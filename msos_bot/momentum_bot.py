"""
Bi-directional Momentum Trading Bot
- Monitors MSOS live trades for entry triggers (+/- 2.5%)
- Trades MSOX using notional orders ($20k)
- Manages trailing stop (0.5%) based on MSOX live trades
"""

import asyncio
import os
from datetime import datetime, time, timedelta
from decimal import Decimal
import pytz
from dotenv import load_dotenv

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    GetOrdersRequest,
    ClosePositionRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest, StockLatestBarRequest
from alpaca.data.timeframe import TimeFrame

# Load environment variables
load_dotenv()

# Configuration
MONITOR_TICKER = "MSOS"  # Ticker to monitor for signals
TRADE_TICKER = "MSOX"    # Ticker to trade
INVERSE_TICKER = "SMSO"  # 1x Inverse ticker (fallback if MSOX not shortable)
NOTIONAL_AMOUNT = 20000  # $20,000 per trade
TRIGGER_THRESHOLD = 2.5  # +/- 2.5% trigger
TRAILING_STOP_PCT = 1.0  # 1.0% trailing stop
TRIGGER_START = time(14, 15)  # 2:15 PM CT
TRIGGER_END = time(14, 30)    # 2:30 PM CT
EXIT_TIME = time(14, 58)      # 2:58 PM CT
TIMEZONE = pytz.timezone('America/Chicago')


class MomentumTradingBot:
    def __init__(self):
        self.api_key = os.getenv('ALPACA_API_KEY')
        self.secret_key = os.getenv('ALPACA_SECRET_KEY')
        
        # Initialize clients
        self.trading_client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=True
        )
        self.data_client = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key
        )
        self.stream = StockDataStream(
            api_key=self.api_key,
            secret_key=self.secret_key
        )
        
        # State variables
        self.previous_close = None
        self.position_entered = False
        self.position_side = None  # 'long' or 'short'
        self.entry_price = None
        self.msos_current_price = None  # MSOS price for entry trigger
        self.msox_current_price = None  # MSOX price for trailing stop
        self.trailing_stop_price = None
        self.highest_price_since_entry = None
        self.lowest_price_since_entry = None
        self.last_log_time = None  # For periodic logging
        self.active_ticker = None  # Track which ticker we're actually trading (MSOX or SMSO)
        self.was_stopped_out = False  # Prevent re-entry after trailing stop hits
        
        print(f"[{self._get_timestamp()}] Bot initialized")
        print(f"[{self._get_timestamp()}] Monitor Ticker: {MONITOR_TICKER}")
        print(f"[{self._get_timestamp()}] Trade Ticker: {TRADE_TICKER}")
        print(f"[{self._get_timestamp()}] Inverse Ticker: {INVERSE_TICKER}")
        print(f"[{self._get_timestamp()}] Paper Trading: Enabled")
    
    def _get_timestamp(self):
        """Get current timestamp in CT"""
        return datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S %Z')
    
    def _get_current_time_ct(self):
        """Get current time in CT timezone"""
        return datetime.now(TIMEZONE).time()
    
    async def fetch_previous_close(self):
        """Fetch previous trading day's closing price for MSOS"""
        print(f"\n[{self._get_timestamp()}] Fetching previous close for {MONITOR_TICKER}...")
        
        try:
            now = datetime.now(TIMEZONE)
            
            # Calculate previous trading day (skip weekends)
            days_to_subtract = 1
            if now.weekday() == 0:  # Monday
                days_to_subtract = 3
            elif now.weekday() == 6:  # Sunday
                days_to_subtract = 2
            
            previous_day = now - timedelta(days=days_to_subtract)
            
            # Set time range for previous trading day (market close at 3:00 PM CT)
            start_time = previous_day.replace(hour=15, minute=0, second=0, microsecond=0)
            end_time = previous_day.replace(hour=16, minute=0, second=0, microsecond=0)
            
            # Request 1-day bar for previous trading day
            request = StockBarsRequest(
                symbol_or_symbols=MONITOR_TICKER,
                timeframe=TimeFrame.Day,
                start=start_time,
                end=end_time
            )
            
            bars = self.data_client.get_stock_bars(request)
            
            if MONITOR_TICKER in bars and len(bars[MONITOR_TICKER]) > 0:
                self.previous_close = float(bars[MONITOR_TICKER][-1].close)
                print(f"[{self._get_timestamp()}] Previous close for {MONITOR_TICKER}: ${self.previous_close:.2f} (Date: {previous_day.strftime('%Y-%m-%d')})")
                return self.previous_close
            else:
                print(f"[{self._get_timestamp()}] WARNING: No bar data found. Falling back to latest bar...")
                request = StockLatestBarRequest(symbol_or_symbols=MONITOR_TICKER)
                latest_bar = self.data_client.get_stock_latest_bar(request)
                self.previous_close = float(latest_bar[MONITOR_TICKER].close)
                print(f"[{self._get_timestamp()}] Previous close for {MONITOR_TICKER}: ${self.previous_close:.2f}")
                return self.previous_close
            
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR fetching previous close: {e}")
            return None
    
    def check_existing_position(self):
        """Check if a position already exists for MSOX or SMSO"""
        try:
            positions = self.trading_client.get_all_positions()
            for position in positions:
                if position.symbol in [TRADE_TICKER, INVERSE_TICKER]:
                    qty = float(position.qty)
                    print(f"[{self._get_timestamp()}] Existing position found: {position.symbol} - {qty} shares")
                    return True
            return False
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR checking positions: {e}")
            return False
    
    def calculate_percent_change(self, current_price):
        """Calculate percent change from previous close"""
        if self.previous_close is None:
            return 0
        return ((current_price - self.previous_close) / self.previous_close) * 100
    
    def check_shortability(self, ticker):
        """Check if a ticker is easy to borrow and shortable"""
        try:
            asset = self.trading_client.get_asset(ticker)
            is_shortable = getattr(asset, 'shortable', False)
            is_easy_to_borrow = getattr(asset, 'easy_to_borrow', False)
            
            print(f"[{self._get_timestamp()}] {ticker} - Shortable: {is_shortable}, Easy to Borrow: {is_easy_to_borrow}")
            return is_shortable and is_easy_to_borrow
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR checking shortability for {ticker}: {e}")
            return False
    
    def should_log_periodic_update(self):
        """Check if 30 seconds have passed since last log"""
        now = datetime.now(TIMEZONE)
        if self.last_log_time is None:
            self.last_log_time = now
            return True
        
        elapsed = (now - self.last_log_time).total_seconds()
        if elapsed >= 30:
            self.last_log_time = now
            return True
        return False
    
    async def place_trade(self, side: OrderSide, ticker=None):
        """Place a notional market order"""
        try:
            # Use provided ticker or default to TRADE_TICKER
            ticker_to_trade = ticker if ticker else TRADE_TICKER
            
            print(f"\n[{self._get_timestamp()}] PLACING {'BUY' if side == OrderSide.BUY else 'SELL'} ORDER")
            print(f"[{self._get_timestamp()}] Ticker: {ticker_to_trade}")
            print(f"[{self._get_timestamp()}] Notional Amount: ${NOTIONAL_AMOUNT}")
            
            order_data = MarketOrderRequest(
                symbol=ticker_to_trade,
                notional=NOTIONAL_AMOUNT,
                side=side,
                time_in_force=TimeInForce.DAY
            )
            
            order = self.trading_client.submit_order(order_data)
            print(f"[{self._get_timestamp()}] Order submitted successfully - Order ID: {order.id}")
            
            self.position_entered = True
            self.position_side = 'long' if side == OrderSide.BUY else 'short'
            self.active_ticker = ticker_to_trade
            
            # Wait a moment for order to fill
            await asyncio.sleep(2)
            
            # Get fill price
            await self.get_fill_price(order.id)
            
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR placing order: {e}")
    
    async def get_fill_price(self, order_id):
        """Get the fill price of the order"""
        try:
            order = self.trading_client.get_order_by_id(order_id)
            if order.filled_avg_price:
                self.entry_price = float(order.filled_avg_price)
                print(f"[{self._get_timestamp()}] Order filled at: ${self.entry_price:.2f}")
                
                # Initialize trailing stop tracking
                self.highest_price_since_entry = self.entry_price
                self.lowest_price_since_entry = self.entry_price
                self.update_trailing_stop(self.entry_price)
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR getting fill price: {e}")
    
    def update_trailing_stop(self, current_price):
        """Update trailing stop loss level based on MSOX price"""
        if self.position_side == 'long':
            # For long positions, track highest price
            if current_price > self.highest_price_since_entry:
                self.highest_price_since_entry = current_price
                self.trailing_stop_price = self.highest_price_since_entry * (1 - TRAILING_STOP_PCT / 100)
                print(f"[{self._get_timestamp()}] {TRADE_TICKER} Trailing stop updated: ${self.trailing_stop_price:.2f} (High: ${self.highest_price_since_entry:.2f})")
        
        elif self.position_side == 'short':
            # For short positions, track lowest price
            if current_price < self.lowest_price_since_entry:
                self.lowest_price_since_entry = current_price
                self.trailing_stop_price = self.lowest_price_since_entry * (1 + TRAILING_STOP_PCT / 100)
                print(f"[{self._get_timestamp()}] {TRADE_TICKER} Trailing stop updated: ${self.trailing_stop_price:.2f} (Low: ${self.lowest_price_since_entry:.2f})")
    
    def check_trailing_stop_hit(self, current_price):
        """Check if trailing stop has been hit based on MSOX price"""
        if self.trailing_stop_price is None:
            return False
        
        if self.position_side == 'long' and current_price <= self.trailing_stop_price:
            print(f"[{self._get_timestamp()}] {TRADE_TICKER} TRAILING STOP HIT! Price: ${current_price:.2f}, Stop: ${self.trailing_stop_price:.2f}")
            return True
        elif self.position_side == 'short' and current_price >= self.trailing_stop_price:
            print(f"[{self._get_timestamp()}] {TRADE_TICKER} TRAILING STOP HIT! Price: ${current_price:.2f}, Stop: ${self.trailing_stop_price:.2f}")
            return True
        
        return False
    
    async def close_all_positions(self):
        """Close all positions at exit time"""
        try:
            print(f"\n[{self._get_timestamp()}] CLOSING ALL POSITIONS (Hard Exit)")
            positions = self.trading_client.get_all_positions()
            
            for position in positions:
                if position.symbol in [TRADE_TICKER, INVERSE_TICKER]:
                    self.trading_client.close_position(position.symbol)
                    print(f"[{self._get_timestamp()}] Closed position: {position.symbol}")
            
            self.position_entered = False
            self.position_side = None
            self.entry_price = None
            self.trailing_stop_price = None
            self.active_ticker = None
            
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR closing positions: {e}")
    
    async def handle_msos_trade(self, data):
        """Handle incoming MSOS trade data - used for entry triggers"""
        try:
            current_time = self._get_current_time_ct()
            self.msos_current_price = float(data.price)
            
            # Calculate percent change
            pct_change = self.calculate_percent_change(self.msos_current_price)
            
            print(f"[{self._get_timestamp()}] {MONITOR_TICKER} Trade: ${self.msos_current_price:.2f} | Change: {pct_change:+.2f}%")
            
            # Check for exit time
            if current_time >= EXIT_TIME:
                if self.position_entered:
                    await self.close_all_positions()
                print(f"[{self._get_timestamp()}] Exit time reached. Bot stopping.")
                await self.stream.stop_ws()
                return
            
            # Entry logic - only if no position and in trigger window
            in_trigger_window = TRIGGER_START <= current_time <= TRIGGER_END
            
            if in_trigger_window and not self.position_entered:
                # Prevent re-entry if already stopped out today
                if self.was_stopped_out:
                    print(f"[{self._get_timestamp()}] Trailing stop already hit today. No re-entry allowed.")
                    return
                
                # Check if position already exists
                if self.check_existing_position():
                    print(f"[{self._get_timestamp()}] Position already exists. Skipping entry.")
                    self.position_entered = True
                    return
                
                # Check for buy trigger
                if pct_change >= TRIGGER_THRESHOLD:
                    print(f"[{self._get_timestamp()}] BUY TRIGGER: {pct_change:+.2f}% >= +{TRIGGER_THRESHOLD}%")
                    await self.place_trade(OrderSide.BUY, TRADE_TICKER)
                
                # Check for short trigger
                elif pct_change <= -TRIGGER_THRESHOLD:
                    print(f"[{self._get_timestamp()}] SHORT TRIGGER: {pct_change:+.2f}% <= -{TRIGGER_THRESHOLD}%")
                    
                    # Check if MSOX is shortable and easy to borrow
                    if self.check_shortability(TRADE_TICKER):
                        print(f"[{self._get_timestamp()}] {TRADE_TICKER} is shortable and easy to borrow - Shorting {TRADE_TICKER}")
                        await self.place_trade(OrderSide.SELL, TRADE_TICKER)
                    else:
                        print(f"[{self._get_timestamp()}] {TRADE_TICKER} is NOT shortable/easy to borrow - Buying {INVERSE_TICKER} instead")
                        await self.place_trade(OrderSide.BUY, INVERSE_TICKER)
        
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR in handle_msos_trade: {e}")
    
    async def handle_msox_trade(self, data):
        """Handle incoming MSOX trade data - used for trailing stop management"""
        try:
            current_time = self._get_current_time_ct()
            self.msox_current_price = float(data.price)
            
            # Only process if we have a position AND we're trading MSOX (not SMSO)
            if not self.position_entered or self.active_ticker != TRADE_TICKER:
                return
            
            # Check for exit time
            if current_time >= EXIT_TIME:
                await self.close_all_positions()
                print(f"[{self._get_timestamp()}] Exit time reached. Bot stopping.")
                await self.stream.stop_ws()
                return
            
            # Update trailing stop based on MSOX price
            self.update_trailing_stop(self.msox_current_price)
            
            # Check if trailing stop hit
            if self.check_trailing_stop_hit(self.msox_current_price):
                self.was_stopped_out = True
                await self.close_all_positions()
                return
            
            # Periodic logging every 30 seconds
            if self.should_log_periodic_update():
                if self.position_side == 'long':
                    print(f"[{self._get_timestamp()}] >>> {TRADE_TICKER} Highest Price Seen: ${self.highest_price_since_entry:.2f} | Current: ${self.msox_current_price:.2f} | Stop: ${self.trailing_stop_price:.2f}")
                elif self.position_side == 'short':
                    print(f"[{self._get_timestamp()}] >>> {TRADE_TICKER} Lowest Price Seen: ${self.lowest_price_since_entry:.2f} | Current: ${self.msox_current_price:.2f} | Stop: ${self.trailing_stop_price:.2f}")
        
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR in handle_msox_trade: {e}")
    
    async def handle_smso_trade(self, data):
        """Handle incoming SMSO trade data - used for trailing stop management when trading inverse"""
        try:
            current_time = self._get_current_time_ct()
            smso_current_price = float(data.price)
            
            # Only process if we have a position AND we're trading SMSO (not MSOX)
            if not self.position_entered or self.active_ticker != INVERSE_TICKER:
                return
            
            # Check for exit time
            if current_time >= EXIT_TIME:
                await self.close_all_positions()
                print(f"[{self._get_timestamp()}] Exit time reached. Bot stopping.")
                await self.stream.stop_ws()
                return
            
            # Update trailing stop based on SMSO price
            self.update_trailing_stop(smso_current_price)
            
            # Check if trailing stop hit
            if self.check_trailing_stop_hit(smso_current_price):
                self.was_stopped_out = True
                await self.close_all_positions()
                return
            
            # Periodic logging every 30 seconds
            if self.should_log_periodic_update():
                if self.position_side == 'long':
                    print(f"[{self._get_timestamp()}] >>> {INVERSE_TICKER} Highest Price Seen: ${self.highest_price_since_entry:.2f} | Current: ${smso_current_price:.2f} | Stop: ${self.trailing_stop_price:.2f}")
        
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR in handle_smso_trade: {e}")
    
    def is_market_open(self):
        """Check if market is open (Monday-Friday, 9:30 AM - 4:00 PM CT)"""
        now_ct = datetime.now(TIMEZONE)
        
        # Check if weekend
        if now_ct.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        # Check if within market hours (9:30 AM ET = 8:30 AM CT to 4:00 PM ET = 3:00 PM CT)
        market_open = time(8, 30)  # 9:30 AM ET
        market_close = time(15, 0)  # 4:00 PM ET
        
        if market_open <= now_ct.time() <= market_close:
            return True
        
        return False
    
    async def wait_for_trading_window(self):
        """Wait until MSOS bot startup (2:00 PM CT) to prepare for trading"""
        while True:
            now_ct = datetime.now(TIMEZONE)
            
            # Check if weekend
            if now_ct.weekday() >= 5:
                # Wait until Monday 2:00 PM CT
                days_until_monday = (7 - now_ct.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 1
                
                next_startup = now_ct.replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
                wait_seconds = (next_startup - now_ct).total_seconds()
                
                print(f"[{self._get_timestamp()}] Market closed (weekend)")
                print(f"[{self._get_timestamp()}] Waiting until Monday {next_startup.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                await asyncio.sleep(min(wait_seconds, 3600))
                continue
            
            # Bot startup time: 2:00 PM CT (to prepare data before 2:15 PM trade window)
            bot_startup = now_ct.replace(hour=14, minute=0, second=0, microsecond=0)
            
            if now_ct < bot_startup:
                wait_seconds = (bot_startup - now_ct).total_seconds()
                print(f"[{self._get_timestamp()}] MSOS bot starts at 2:00 PM CT (15 min before trade window)")
                print(f"[{self._get_timestamp()}] Waiting {wait_seconds:.0f} seconds...")
                await asyncio.sleep(min(wait_seconds, 3600))
                continue
            
            # Check if after exit time (2:58 PM CT)
            if now_ct.time() >= EXIT_TIME:
                # Wait until tomorrow 2:00 PM
                next_startup = bot_startup + timedelta(days=1)
                wait_seconds = (next_startup - now_ct).total_seconds()
                
                print(f"[{self._get_timestamp()}] Trading window closed for today")
                print(f"[{self._get_timestamp()}] Waiting until tomorrow {next_startup.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                await asyncio.sleep(min(wait_seconds, 3600))
                continue
            
            # Bot is ready to start!
            print(f"[{self._get_timestamp()}] Bot startup time reached - fetching data and preparing for 2:15 PM trade window")
            return
    
    async def run(self):
        """Main bot loop"""
        print(f"\n{'='*60}")
        print(f"MOMENTUM TRADING BOT STARTED")
        print(f"{'='*60}\n")
        
        # Wait for trading window
        await self.wait_for_trading_window()
        
        # Fetch previous close
        if await self.fetch_previous_close() is None:
            print(f"[{self._get_timestamp()}] Failed to fetch previous close. Exiting.")
            return
        
        # Calculate trigger levels
        buy_trigger = self.previous_close * (1 + TRIGGER_THRESHOLD / 100)
        short_trigger = self.previous_close * (1 - TRIGGER_THRESHOLD / 100)
        
        print(f"\n[{self._get_timestamp()}] TRIGGER LEVELS:")
        print(f"[{self._get_timestamp()}] Buy Trigger: ${buy_trigger:.2f} (+{TRIGGER_THRESHOLD}%)")
        print(f"[{self._get_timestamp()}] Short Trigger: ${short_trigger:.2f} (-{TRIGGER_THRESHOLD}%)")
        print(f"[{self._get_timestamp()}] Trigger Window: {TRIGGER_START} - {TRIGGER_END} CT")
        print(f"[{self._get_timestamp()}] Hard Exit: {EXIT_TIME} CT")
        print(f"[{self._get_timestamp()}] Trailing Stop: {TRAILING_STOP_PCT}%\n")
        
        # Subscribe to live trade data for all tickers
        self.stream.subscribe_trades(self.handle_msos_trade, MONITOR_TICKER)
        self.stream.subscribe_trades(self.handle_msox_trade, TRADE_TICKER)
        self.stream.subscribe_trades(self.handle_smso_trade, INVERSE_TICKER)
        
        print(f"[{self._get_timestamp()}] Subscribed to {MONITOR_TICKER} live trade stream (entry triggers)")
        print(f"[{self._get_timestamp()}] Subscribed to {TRADE_TICKER} live trade stream (trailing stop)")
        print(f"[{self._get_timestamp()}] Subscribed to {INVERSE_TICKER} live trade stream (trailing stop - inverse)")
        print(f"[{self._get_timestamp()}] Monitoring for signals...\n")
        
        # Run the stream
        await self.stream.run()


async def main():
    bot = MomentumTradingBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
