"""
Bi-directional Momentum Trading Bot
- Monitors MSOS live trades for entry triggers (+/- 2.5%)
- Trades MSOX using notional orders ($20k)
- Manages trailing stop (0.5%) based on MSOX live trades
"""

import asyncio
import os
import sys
import random
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
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
MONITOR_TICKER = "MSOS"  # Ticker to monitor for signals AND short for negative momentum
TRADE_TICKER = "MSOX"    # Ticker to trade for LONG signals (3x leveraged)
NOTIONAL_AMOUNT = 20000  # $20,000 per trade
TRIGGER_THRESHOLD = 2.5  # +/- 2.5% trigger
TRAILING_STOP_PCT = 1.0  # 1.0% trailing stop
TRIGGER_START = time(14, 15)  # 2:15 PM CT
TRIGGER_END = time(14, 30)    # 2:30 PM CT
EXIT_TIME = time(14, 58)      # 2:58 PM CT
TIMEZONE = pytz.timezone('America/Chicago')

# Startup coordination
RESTART_TRACKER_FILE = "/tmp/msos_bot_restart_count.txt"


def log_and_flush(message):
    """Print and immediately flush to ensure logs appear in Railway"""
    print(message, flush=True)


async def handle_connection_limit_backoff():
    """
    Implement exponential backoff if we've been restarting repeatedly.
    This prevents Railway restart storms when connection limit is exceeded.
    """
    tracker_path = Path(RESTART_TRACKER_FILE)
    
    try:
        if tracker_path.exists():
            content = tracker_path.read_text().strip()
            if content:
                last_attempt_time, attempt_count = content.split(',')
                last_attempt = float(last_attempt_time)
                attempts = int(attempt_count)
                
                # If last attempt was within 5 minutes, increment counter
                if (datetime.now().timestamp() - last_attempt) < 300:
                    attempts += 1
                else:
                    # More than 5 minutes passed, reset counter
                    attempts = 1
            else:
                attempts = 1
        else:
            attempts = 1
        
        # Write current attempt
        tracker_path.write_text(f"{datetime.now().timestamp()},{attempts}")
        
        # If we've had multiple recent failures, add exponential backoff
        if attempts > 1:
            # Exponential backoff: 5s, 10s, 20s, 40s, 60s (max)
            backoff_seconds = min(60, 5 * (2 ** (attempts - 2)))
            # Add jitter to prevent thundering herd
            jitter = random.uniform(0, backoff_seconds * 0.3)
            total_delay = backoff_seconds + jitter
            
            log_and_flush(f"[INFO] Recent restart detected (attempt #{attempts})")
            log_and_flush(f"[INFO] Waiting {total_delay:.1f}s to prevent connection storms...")
            await asyncio.sleep(total_delay)
        
        return attempts
        
    except Exception as e:
        log_and_flush(f"[WARNING] Backoff tracker error: {e}")
        return 1


async def test_alpaca_connection(trading_client):
    """
    Test Alpaca API connection before subscribing to websockets.
    Fails fast if connection is not available.
    """
    try:
        log_and_flush("[INFO] Testing Alpaca API connection...")
        # Simple API call to verify credentials and connection
        account = trading_client.get_account()
        log_and_flush(f"[INFO] Connection successful - Account: {account.account_number}")
        return True
    except Exception as e:
        log_and_flush(f"[ERROR] Alpaca API connection test failed: {e}")
        log_and_flush(f"[ERROR] Cannot proceed without API access")
        return False


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
        print(f"[{self._get_timestamp()}] Long Trade Ticker: {TRADE_TICKER} (3x leveraged)")
        print(f"[{self._get_timestamp()}] Short Trade Ticker: {MONITOR_TICKER} (will short if ETB)")
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
        """Check if a position already exists for MSOX or MSOS"""
        try:
            positions = self.trading_client.get_all_positions()
            for position in positions:
                if position.symbol in [TRADE_TICKER, MONITOR_TICKER]:
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
            print(f"[{self._get_timestamp()}] Order submitted - Order ID: {order.id}")
            
            # Wait for order to fill
            await asyncio.sleep(3)
            
            # Verify order filled before setting position state
            fill_success = await self.get_fill_price(order.id)
            
            if fill_success:
                # Only set position state AFTER confirming fill
                self.position_entered = True
                self.position_side = 'long' if side == OrderSide.BUY else 'short'
                self.active_ticker = ticker_to_trade
                print(f"[{self._get_timestamp()}] SUCCESS: Position entered successfully")
            else:
                print(f"[{self._get_timestamp()}] FAILED: Position NOT entered - order did not fill")
            
        except Exception as e:
            error_msg = str(e)
            log_and_flush(f"[{self._get_timestamp()}] !!!!! ERROR placing order: {error_msg} !!!!!")
            log_and_flush(f"[{self._get_timestamp()}] Error type: {type(e).__name__}")
            log_and_flush(f"[{self._get_timestamp()}] Ticker: {ticker_to_trade}, Notional: ${notional}, Side: {side}")
            
            # Check if it's a connection limit issue during order placement
            if "connection limit" in error_msg.lower() or "429" in error_msg:
                log_and_flush(f"[{self._get_timestamp()}] CONNECTION LIMIT ERROR during order placement")
                log_and_flush(f"[{self._get_timestamp()}] This means another bot is connected to Alpaca")
                log_and_flush(f"[{self._get_timestamp()}] Check Railway dashboard for multiple replicas")
            
            log_and_flush(f"[{self._get_timestamp()}] Position NOT entered due to error")
    
    async def get_fill_price(self, order_id):
        """Get the fill price of the order and verify it filled"""
        try:
            order = self.trading_client.get_order_by_id(order_id)
            
            if order.status == 'filled' and order.filled_avg_price:
                self.entry_price = float(order.filled_avg_price)
                print(f"[{self._get_timestamp()}] SUCCESS: ORDER FILLED at: ${self.entry_price:.2f}")
                
                # Initialize trailing stop tracking
                self.highest_price_since_entry = self.entry_price
                self.lowest_price_since_entry = self.entry_price
                self.update_trailing_stop(self.entry_price)
                
                return True
            else:
                print(f"[{self._get_timestamp()}] FAILED: ORDER NOT FILLED - Status: {order.status}")
                
                # Try to cancel if still pending
                try:
                    if order.status in ['pending_new', 'accepted', 'new', 'partially_filled']:
                        self.trading_client.cancel_order_by_id(order_id)
                        print(f"[{self._get_timestamp()}] Order cancelled")
                except:
                    pass
                
                return False
                
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR getting fill price: {e}")
            return False
    
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
        """Close all positions at exit time and log final P&L"""
        try:
            print(f"\n[{self._get_timestamp()}] CLOSING ALL POSITIONS (Hard Exit)")
            positions = self.trading_client.get_all_positions()
            
            for position in positions:
                if position.symbol in [TRADE_TICKER, MONITOR_TICKER]:
                    # Log final P&L before closing
                    final_pl = float(position.unrealized_pl)
                    final_pl_pct = float(position.unrealized_plpc) * 100
                    current_price = float(position.current_price)
                    qty = float(position.qty)
                    
                    print(f"[{self._get_timestamp()}] === FINAL TRADE SUMMARY ===")
                    print(f"[{self._get_timestamp()}] Symbol: {position.symbol}")
                    print(f"[{self._get_timestamp()}] Entry Price: ${self.entry_price:.2f}")
                    print(f"[{self._get_timestamp()}] Exit Price: ${current_price:.2f}")
                    print(f"[{self._get_timestamp()}] Shares/Notional: {int(qty)} shares")
                    print(f"[{self._get_timestamp()}] Final P&L: ${final_pl:.2f} ({final_pl_pct:+.2f}%)")
                    print(f"[{self._get_timestamp()}] ==========================")
                    
                    # Close the position
                    self.trading_client.close_position(position.symbol)
                    print(f"[{self._get_timestamp()}] Position closed successfully")
            
            self.position_entered = False
            self.position_side = None
            self.entry_price = None
            self.trailing_stop_price = None
            self.active_ticker = None
            
        except Exception as e:
            print(f"[{self._get_timestamp()}] ERROR closing positions: {e}")
    
    async def handle_msos_trade(self, data):
        """Handle incoming MSOS trade data - used for entry triggers AND short position monitoring"""
        try:
            current_time = self._get_current_time_ct()
            self.msos_current_price = float(data.price)
            
            # Calculate percent change
            pct_change = self.calculate_percent_change(self.msos_current_price)
            
            print(f"[{self._get_timestamp()}] {MONITOR_TICKER} Trade: ${self.msos_current_price:.2f} | Change: {pct_change:+.2f}%")
            
            # If we have a SHORT position in MSOS, manage trailing stop
            if self.position_entered and self.active_ticker == MONITOR_TICKER:
                self.update_trailing_stop(self.msos_current_price)
                
                # Check if trailing stop hit for short MSOS position
                if self.check_trailing_stop_hit(self.msos_current_price):
                    self.was_stopped_out = True
                    await self.close_all_positions()
                    return
                
                # Periodic logging for MSOS short position
                if self.should_log_periodic_update():
                    if self.position_side == 'short':
                        print(f"[{self._get_timestamp()}] >>> {MONITOR_TICKER} Lowest Price Seen: ${self.lowest_price_since_entry:.2f} | Current: ${self.msos_current_price:.2f} | Stop: ${self.trailing_stop_price:.2f}")
            
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
                    
                    # Check if MSOS is shortable and easy to borrow
                    if self.check_shortability(MONITOR_TICKER):
                        print(f"[{self._get_timestamp()}] {MONITOR_TICKER} is shortable and easy to borrow - Shorting {MONITOR_TICKER}")
                        await self.place_trade(OrderSide.SELL, MONITOR_TICKER)
                    else:
                        print(f"[{self._get_timestamp()}] WARNING: {MONITOR_TICKER} is NOT shortable or ETB")
                        print(f"[{self._get_timestamp()}] SKIPPING short entry")
                        self.was_stopped_out = True  # Prevent further entries today
        
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
        """Check if we're in trading window, exit if not (Railway will restart)"""
        now_ct = datetime.now(TIMEZONE)
        current_time = now_ct.time()
        
        # Bot startup time: 2:01 PM CT
        bot_startup = time(14, 1)
        
        # If we're at or after 2:01 PM, we're good to proceed
        if current_time >= bot_startup:
            print(f"[{self._get_timestamp()}] Bot startup time reached - fetching data and preparing for 2:15 PM trade window")
            return True
        
        # Before 2:01 PM - calculate wait time
        bot_startup_dt = now_ct.replace(hour=14, minute=1, second=0, microsecond=0)
        wait_seconds = (bot_startup_dt - now_ct).total_seconds()
        
        # If more than 5 minutes away, exit and let Railway restart
        if wait_seconds > 300:
            print(f"[{self._get_timestamp()}] MSOS bot starts at 2:01 PM CT")
            print(f"[{self._get_timestamp()}] {wait_seconds:.0f} seconds until startup")
            print(f"[{self._get_timestamp()}] Exiting - Railway will restart closer to 2:01 PM")
            await asyncio.sleep(30)
            return False
        else:
            # Less than 5 minutes - wait for it
            print(f"[{self._get_timestamp()}] MSOS bot starts at 2:01 PM CT (in {wait_seconds:.0f} seconds)")
            print(f"[{self._get_timestamp()}] Waiting for startup time...")
            await asyncio.sleep(wait_seconds)
            print(f"[{self._get_timestamp()}] Bot startup time reached")
            return True
    
    async def run(self):
        """Main bot loop"""
        log_and_flush(f"\n{'='*60}")
        log_and_flush(f"MOMENTUM TRADING BOT STARTED")
        log_and_flush(f"{'='*60}\n")
        
        # STEP 1: Implement exponential backoff if we've been restarting repeatedly
        attempt_num = await handle_connection_limit_backoff()
        if attempt_num > 5:
            log_and_flush(f"[ERROR] Too many restart attempts ({attempt_num})")
            log_and_flush(f"[ERROR] Possible causes:")
            log_and_flush(f"[ERROR]   - Multiple Railway replicas running")
            log_and_flush(f"[ERROR]   - NVDA bot still holding the connection")
            log_and_flush(f"[ERROR]   - Alpaca API issues")
            log_and_flush(f"[INFO] Exiting - check Railway dashboard for multiple replicas")
            await asyncio.sleep(60)
            return
        
        # STEP 2: Check if we should run right now (prevent connecting to websockets when not needed)
        now_ct = datetime.now(TIMEZONE)
        current_time_ct = now_ct.time()
        
        # CRITICAL: Don't connect to Alpaca if NVDA bot should be running (before 2:00 PM CST)
        # This prevents connection limit exceeded errors
        if current_time_ct < time(14, 0):
            log_and_flush(f"[{self._get_timestamp()}] Current time: {now_ct.strftime('%H:%M:%S %Z')}")
            log_and_flush(f"[{self._get_timestamp()}] MSOS bot window not yet open (starts 2:01 PM CST)")
            log_and_flush(f"[{self._get_timestamp()}] NVDA bot time slot - exiting to avoid connection conflict")
            log_and_flush(f"[{self._get_timestamp()}] Railway will restart this bot and check again")
            await asyncio.sleep(30)
            return
        
        # Check if after exit time
        if current_time_ct >= EXIT_TIME:
            log_and_flush(f"[{self._get_timestamp()}] Current time: {now_ct.strftime('%H:%M:%S %Z')}")
            log_and_flush(f"[{self._get_timestamp()}] MSOS bot window closed for today (closes 2:58 PM CST)")
            log_and_flush(f"[{self._get_timestamp()}] Exiting - Railway will restart tomorrow")
            await asyncio.sleep(30)
            return
        
        # STEP 3: Wait for trading window (will only wait if between 2:00-2:01 PM)
        if not await self.wait_for_trading_window():
            return  # Exit if not in trading window
        
        # STEP 4: Test Alpaca API connection BEFORE subscribing to websockets
        if not await test_alpaca_connection(self.trading_client):
            log_and_flush(f"[ERROR] Cannot connect to Alpaca API - exiting")
            await asyncio.sleep(30)
            return
        
        # Fetch previous close
        if await self.fetch_previous_close() is None:
            print(f"[{self._get_timestamp()}] Failed to fetch previous close. Exiting.")
            return
        
        # Check for existing positions (in case of bot restart)
        print(f"\n[{self._get_timestamp()}] Checking for existing positions...")
        if self.check_existing_position():
            print(f"[{self._get_timestamp()}] WARNING: Existing position found at startup")
            print(f"[{self._get_timestamp()}] Bot will monitor existing position but not enter new trades today")
            self.position_entered = True
            self.was_stopped_out = True
        else:
            print(f"[{self._get_timestamp()}] No existing positions found - ready to trade")
        
        # Calculate trigger levels
        buy_trigger = self.previous_close * (1 + TRIGGER_THRESHOLD / 100)
        short_trigger = self.previous_close * (1 - TRIGGER_THRESHOLD / 100)
        
        print(f"\n[{self._get_timestamp()}] TRIGGER LEVELS:")
        print(f"[{self._get_timestamp()}] Buy Trigger: ${buy_trigger:.2f} (+{TRIGGER_THRESHOLD}%)")
        print(f"[{self._get_timestamp()}] Short Trigger: ${short_trigger:.2f} (-{TRIGGER_THRESHOLD}%)")
        print(f"[{self._get_timestamp()}] Trigger Window: {TRIGGER_START} - {TRIGGER_END} CT")
        print(f"[{self._get_timestamp()}] Hard Exit: {EXIT_TIME} CT")
        print(f"[{self._get_timestamp()}] Trailing Stop: {TRAILING_STOP_PCT}%\n")
        
        # Subscribe to live trade data
        # MSOS stream: Used for entry triggers AND short position monitoring
        # MSOX stream: Used for long position monitoring
        self.stream.subscribe_trades(self.handle_msos_trade, MONITOR_TICKER)
        self.stream.subscribe_trades(self.handle_msox_trade, TRADE_TICKER)
        
        print(f"[{self._get_timestamp()}] Subscribed to {MONITOR_TICKER} live trade stream (entry triggers + short position)")
        print(f"[{self._get_timestamp()}] Subscribed to {TRADE_TICKER} live trade stream (long position)")
        print(f"[{self._get_timestamp()}] Monitoring for signals...\n")
        
        # Run the stream - use _run_forever() directly since we already have an event loop
        # The stream.run() method calls asyncio.run() which fails when a loop is already running
        try:
            await self.stream._run_forever()
        except ValueError as e:
            if "connection limit exceeded" in str(e):
                print(f"\n[{self._get_timestamp()}] ERROR: Connection limit exceeded")
                print(f"[{self._get_timestamp()}] This means another bot instance is using the Alpaca connection")
                print(f"[{self._get_timestamp()}] Possible causes:")
                print(f"[{self._get_timestamp()}]   1. Railway running multiple replicas of this service")
                print(f"[{self._get_timestamp()}]   2. NVDA bot still connected (should have exited)")
                print(f"[{self._get_timestamp()}]   3. Old deployment still running")
                print(f"[{self._get_timestamp()}] Exiting - Railway will restart in 30 seconds")
                await asyncio.sleep(30)
                return
            else:
                raise


async def main():
    bot = MomentumTradingBot()
    await bot.run()


if __name__ == "__main__":
    # Handle both Railway and local environments
    # IMPORTANT: Always create a NEW event loop to avoid deprecated loop issues
    # The deprecated get_event_loop() doesn't support modern websocket features
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user")
    finally:
        # Clean up
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except:
            pass
        try:
            loop.close()
        except:
            pass
