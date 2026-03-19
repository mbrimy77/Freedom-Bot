"""
NVDA 15-Minute Opening Range Breakout (ORB) Strategy
- Monitors NVDA for 15-min ORB (9:30-9:45 AM ET)
- Trades NVDL (2x Long) or NVD (2x Short) based on 5-min candle closes
- Position sizing: 1.5% move = $300 loss on $20k account
- Dual-stage exit: 1.5% hard stop → 3% profit triggers 1% trailing stop
- Hard exit at 2:00 PM CST (Golden Gap for MSOS bot at 2:15 PM)
- Maximum one trade per day
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
    StopLossRequest,
    TrailingStopOrderRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load environment variables
load_dotenv()

# Configuration
MONITOR_TICKER = "NVDA"        # Ticker to monitor for signals
LONG_TICKER = "NVDL"           # 2x Long ETF
SHORT_TICKER = "NVD"           # 2x Short ETF
ACCOUNT_SIZE = 20000           # $20,000 account
RISK_AMOUNT = 300              # $300 max loss per trade
HARD_STOP_PCT = 1.5            # 1.5% hard stop loss
PROFIT_TARGET_PCT = 3.0        # 3% profit to activate trailing stop
TRAILING_STOP_PCT = 1.0        # 1% trailing stop after profit target hit
MAX_TRADES_PER_DAY = 1         # Maximum one trade per day

# Time windows (ET = Eastern Time, CST = Central Time)
ORB_START = time(9, 30)        # 9:30 AM ET (ORB start)
ORB_END = time(9, 45)          # 9:45 AM ET (ORB end)
TRADING_START = time(9, 45)    # 9:45 AM ET (start monitoring for breakouts)
GOLDEN_GAP_EXIT = time(14, 0)  # 2:00 PM CST (hard exit for MSOS buffer)

TIMEZONE_ET = pytz.timezone('America/New_York')
TIMEZONE_CST = pytz.timezone('America/Chicago')


class NVDAOpeningRangeBot:
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
        self.orb_high = None
        self.orb_low = None
        self.orb_established = False
        self.position_entered = False
        self.position_side = None  # 'long' or 'short'
        self.entry_price = None
        self.entry_ticker = None
        self.shares = 0
        self.stop_loss_order_id = None
        self.profit_target_hit = False
        self.trades_today = 0
        self.last_5min_candle_time = None
        self.current_5min_high = None
        self.current_5min_low = None
        self.current_5min_close = None
        
        # Real-time price tracking for ETFs
        self.nvdl_current_price = None  # NVDL (2x Long) real-time price
        self.nvd_current_price = None   # NVD (2x Short) real-time price
        self.highest_price_since_entry = None
        self.lowest_price_since_entry = None
        self.last_log_time = None  # For periodic logging
        
        print(f"[{self._get_timestamp_et()}] NVDA ORB Bot initialized")
        print(f"[{self._get_timestamp_et()}] Monitor Ticker: {MONITOR_TICKER}")
        print(f"[{self._get_timestamp_et()}] Long Ticker: {LONG_TICKER} (2x)")
        print(f"[{self._get_timestamp_et()}] Short Ticker: {SHORT_TICKER} (2x)")
        print(f"[{self._get_timestamp_et()}] Account Size: ${ACCOUNT_SIZE:,}")
        print(f"[{self._get_timestamp_et()}] Risk Per Trade: ${RISK_AMOUNT}")
        print(f"[{self._get_timestamp_et()}] Hard Stop: {HARD_STOP_PCT}%")
        print(f"[{self._get_timestamp_et()}] Profit Target: {PROFIT_TARGET_PCT}%")
        print(f"[{self._get_timestamp_et()}] Trailing Stop: {TRAILING_STOP_PCT}%")
        print(f"[{self._get_timestamp_et()}] Paper Trading: Enabled")
    
    def _get_timestamp_et(self):
        """Get current timestamp in ET"""
        return datetime.now(TIMEZONE_ET).strftime('%Y-%m-%d %H:%M:%S %Z')
    
    def _get_timestamp_cst(self):
        """Get current timestamp in CST"""
        return datetime.now(TIMEZONE_CST).strftime('%Y-%m-%d %H:%M:%S %Z')
    
    def _get_current_time_et(self):
        """Get current time in ET timezone"""
        return datetime.now(TIMEZONE_ET).time()
    
    def _get_current_time_cst(self):
        """Get current time in CST timezone"""
        return datetime.now(TIMEZONE_CST).time()
    
    def is_market_open(self):
        """Check if market is open (Monday-Friday, 9:30 AM - 4:00 PM ET)"""
        now_et = datetime.now(TIMEZONE_ET)
        
        # Check if weekend
        if now_et.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        # Check if within market hours (9:30 AM - 4:00 PM ET)
        market_open = time(9, 30)
        market_close = time(16, 0)
        
        if market_open <= now_et.time() <= market_close:
            return True
        
        return False
    
    async def wait_for_market_open(self):
        """Wait until market opens (9:30 AM ET on next trading day)"""
        while True:
            now_et = datetime.now(TIMEZONE_ET)
            
            # Check if weekend
            if now_et.weekday() >= 5:  # Saturday or Sunday
                # Wait until Monday 9:30 AM
                days_until_monday = (7 - now_et.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 1  # If Sunday, wait 1 day
                
                next_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0) + timedelta(days=days_until_monday)
                wait_seconds = (next_open - now_et).total_seconds()
                
                print(f"[{self._get_timestamp_et()}] Market closed (weekend)")
                print(f"[{self._get_timestamp_et()}] Waiting until Monday {next_open.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                # Sleep in chunks to avoid blocking
                await asyncio.sleep(min(wait_seconds, 3600))  # Sleep max 1 hour at a time
                continue
            
            # Check if before market open today
            market_open_time = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
            
            if now_et < market_open_time:
                wait_seconds = (market_open_time - now_et).total_seconds()
                print(f"[{self._get_timestamp_et()}] Market opens at 9:30 AM ET")
                print(f"[{self._get_timestamp_et()}] Waiting {wait_seconds:.0f} seconds...")
                await asyncio.sleep(min(wait_seconds, 3600))
                continue
            
            # Check if after market close
            market_close_time = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            
            if now_et > market_close_time:
                # Market closed for today, wait until tomorrow 9:30 AM
                next_open = market_open_time + timedelta(days=1)
                wait_seconds = (next_open - now_et).total_seconds()
                
                print(f"[{self._get_timestamp_et()}] Market closed for today")
                print(f"[{self._get_timestamp_et()}] Waiting until tomorrow {next_open.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                await asyncio.sleep(min(wait_seconds, 3600))
                continue
            
            # Market is open!
            print(f"[{self._get_timestamp_et()}] Market is open - ready to trade")
            return
    
    async def establish_opening_range(self):
        """Fetch 15-minute opening range (9:30-9:45 AM ET)"""
        print(f"\n[{self._get_timestamp_et()}] Establishing 15-minute Opening Range...")
        
        max_retries = 5
        retry_delay = 60  # 60 seconds between retries
        
        for attempt in range(max_retries):
            try:
                now_et = datetime.now(TIMEZONE_ET)
                
                # Set time range for ORB (9:30 AM - 9:45 AM ET today)
                orb_start_time = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
                orb_end_time = now_et.replace(hour=9, minute=45, second=0, microsecond=0)
                
                # If current time is before ORB end, wait
                if now_et < orb_end_time:
                    wait_seconds = (orb_end_time - now_et).total_seconds()
                    print(f"[{self._get_timestamp_et()}] Waiting {wait_seconds:.0f} seconds for ORB to complete...")
                    await asyncio.sleep(wait_seconds + 10)  # Add 10 seconds buffer
                
                # Update time after waiting
                now_et = datetime.now(TIMEZONE_ET)
                print(f"[{self._get_timestamp_et()}] Fetching ORB data (attempt {attempt + 1}/{max_retries})...")
                
                # Fetch 1-minute bars for the opening range period
                # We'll get all 1-min bars from 9:30-9:45 to calculate high/low
                request = StockBarsRequest(
                    symbol_or_symbols=MONITOR_TICKER,
                    timeframe=TimeFrame.Minute,
                    start=orb_start_time,
                    end=orb_end_time,
                    limit=20  # Request up to 20 bars (15 min period)
                )
                
                bars = self.data_client.get_stock_bars(request)
                
                if MONITOR_TICKER in bars and len(bars[MONITOR_TICKER]) > 0:
                    bar_list = bars[MONITOR_TICKER]
                    print(f"[{self._get_timestamp_et()}] Received {len(bar_list)} bars for ORB calculation")
                    
                    self.orb_high = max([float(bar.high) for bar in bar_list])
                    self.orb_low = min([float(bar.low) for bar in bar_list])
                    self.orb_established = True
                    
                    print(f"[{self._get_timestamp_et()}] Opening Range Established (9:30-9:45 AM ET)")
                    print(f"[{self._get_timestamp_et()}] ORB High: ${self.orb_high:.2f}")
                    print(f"[{self._get_timestamp_et()}] ORB Low: ${self.orb_low:.2f}")
                    print(f"[{self._get_timestamp_et()}] ORB Range: ${self.orb_high - self.orb_low:.2f}")
                    return True
                else:
                    print(f"[{self._get_timestamp_et()}] WARNING: No bar data returned (attempt {attempt + 1}/{max_retries})")
                    
                    if attempt < max_retries - 1:
                        print(f"[{self._get_timestamp_et()}] Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                    else:
                        print(f"[{self._get_timestamp_et()}] ERROR: Failed to get ORB data after {max_retries} attempts")
                        return False
                
            except Exception as e:
                print(f"[{self._get_timestamp_et()}] ERROR establishing ORB (attempt {attempt + 1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    print(f"[{self._get_timestamp_et()}] Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    print(f"[{self._get_timestamp_et()}] ERROR: Failed to establish ORB after {max_retries} attempts")
                    return False
        
        return False
    
    def calculate_position_size(self, entry_price):
        """
        Calculate shares based on:
        - $20,000 account
        - 1.5% move = $300 loss
        - ETF is 2x leveraged
        
        Formula: shares = risk_amount / (entry_price * stop_pct * leverage)
        """
        leverage = 2.0
        stop_distance = entry_price * (HARD_STOP_PCT / 100)
        
        # For 2x ETF, a 1.5% move in the underlying = ~3% move in the ETF
        # So we need: shares * entry_price * 0.015 * 2 = 300
        # shares = 300 / (entry_price * 0.015 * 2)
        shares = RISK_AMOUNT / (entry_price * (HARD_STOP_PCT / 100) * leverage)
        shares = int(shares)  # Round down to whole shares
        
        notional_value = shares * entry_price
        max_loss = shares * entry_price * (HARD_STOP_PCT / 100) * leverage
        
        print(f"[{self._get_timestamp_et()}] Position Sizing:")
        print(f"[{self._get_timestamp_et()}]   Entry Price: ${entry_price:.2f}")
        print(f"[{self._get_timestamp_et()}]   Shares: {shares}")
        print(f"[{self._get_timestamp_et()}]   Notional Value: ${notional_value:.2f}")
        print(f"[{self._get_timestamp_et()}]   Expected Max Loss: ${max_loss:.2f}")
        
        return shares
    
    def check_existing_position(self):
        """Check if a position already exists for NVDL or NVD"""
        try:
            positions = self.trading_client.get_all_positions()
            for position in positions:
                if position.symbol in [LONG_TICKER, SHORT_TICKER]:
                    qty = float(position.qty)
                    print(f"[{self._get_timestamp_et()}] Existing position found: {position.symbol} - {qty} shares")
                    return True
            return False
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR checking positions: {e}")
            return False
    
    async def place_trade_with_stop(self, ticker: str, side: OrderSide, entry_price: float):
        """Place trade with bracket order (entry + stop loss)"""
        try:
            # Calculate position size
            shares = self.calculate_position_size(entry_price)
            
            if shares <= 0:
                print(f"[{self._get_timestamp_et()}] ERROR: Invalid position size")
                return False
            
            # Calculate stop loss price
            if side == OrderSide.BUY:
                stop_price = entry_price * (1 - HARD_STOP_PCT / 100)
            else:
                stop_price = entry_price * (1 + HARD_STOP_PCT / 100)
            
            print(f"\n[{self._get_timestamp_et()}] PLACING {'LONG' if side == OrderSide.BUY else 'SHORT'} ORDER")
            print(f"[{self._get_timestamp_et()}] Ticker: {ticker}")
            print(f"[{self._get_timestamp_et()}] Shares: {shares}")
            print(f"[{self._get_timestamp_et()}] Entry Price: ${entry_price:.2f}")
            print(f"[{self._get_timestamp_et()}] Stop Loss: ${stop_price:.2f} ({HARD_STOP_PCT}%)")
            
            # Submit market order with stop loss
            order_data = MarketOrderRequest(
                symbol=ticker,
                qty=shares,
                side=side,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                stop_loss=StopLossRequest(stop_price=stop_price)
            )
            
            order = self.trading_client.submit_order(order_data)
            print(f"[{self._get_timestamp_et()}] Order submitted - Order ID: {order.id}")
            
            self.position_entered = True
            self.position_side = 'long' if side == OrderSide.BUY else 'short'
            self.entry_ticker = ticker
            self.entry_price = entry_price
            self.shares = shares
            self.trades_today += 1
            
            # Initialize price tracking for trailing stop
            self.highest_price_since_entry = entry_price
            self.lowest_price_since_entry = entry_price
            
            # Wait for order to fill
            await asyncio.sleep(2)
            
            # Get stop loss order ID
            await self.get_child_orders(order.id)
            
            return True
            
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR placing order: {e}")
            return False
    
    async def get_child_orders(self, parent_order_id):
        """Get child orders (stop loss) from bracket order"""
        try:
            await asyncio.sleep(1)
            orders = self.trading_client.get_orders()
            
            for order in orders:
                if hasattr(order, 'legs') and order.id == parent_order_id:
                    for leg in order.legs:
                        leg_order = self.trading_client.get_order_by_id(leg.id)
                        if leg_order.order_type.value == 'stop':
                            self.stop_loss_order_id = leg.id
                            print(f"[{self._get_timestamp_et()}] Stop Loss Order ID: {self.stop_loss_order_id}")
                            break
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR getting child orders: {e}")
    
    def should_log_periodic_update(self):
        """Check if 30 seconds have passed since last log"""
        now = datetime.now(TIMEZONE_ET)
        if self.last_log_time is None:
            self.last_log_time = now
            return True
        
        elapsed = (now - self.last_log_time).total_seconds()
        if elapsed >= 30:
            self.last_log_time = now
            return True
        return False
    
    async def check_profit_target(self, current_price):
        """Check if profit target reached and upgrade to trailing stop"""
        if self.profit_target_hit or not self.position_entered:
            return
        
        try:
            # Calculate current P&L
            if self.position_side == 'long':
                price_change = current_price - self.entry_price
            else:
                price_change = self.entry_price - current_price
            
            unrealized_pl = price_change * self.shares
            unrealized_pl_pct = (price_change / self.entry_price) * 100
            
            # Check if profit target hit
            if unrealized_pl >= (ACCOUNT_SIZE * PROFIT_TARGET_PCT / 100):
                print(f"\n[{self._get_timestamp_et()}] PROFIT TARGET HIT! ${unrealized_pl:.2f} >= ${ACCOUNT_SIZE * PROFIT_TARGET_PCT / 100:.2f}")
                print(f"[{self._get_timestamp_et()}] Upgrading to {TRAILING_STOP_PCT}% Trailing Stop...")
                
                # Cancel existing stop loss
                if self.stop_loss_order_id:
                    try:
                        self.trading_client.cancel_order_by_id(self.stop_loss_order_id)
                        print(f"[{self._get_timestamp_et()}] Hard stop canceled")
                    except Exception as e:
                        print(f"[{self._get_timestamp_et()}] ERROR canceling stop: {e}")
                
                # Place trailing stop order
                try:
                    trailing_stop_request = TrailingStopOrderRequest(
                        symbol=self.entry_ticker,
                        qty=self.shares,
                        side=OrderSide.SELL if self.position_side == 'long' else OrderSide.BUY,
                        time_in_force=TimeInForce.DAY,
                        trail_percent=TRAILING_STOP_PCT
                    )
                    
                    trailing_order = self.trading_client.submit_order(trailing_stop_request)
                    self.stop_loss_order_id = trailing_order.id
                    self.profit_target_hit = True
                    
                    print(f"[{self._get_timestamp_et()}] Trailing Stop activated - Order ID: {trailing_order.id}")
                    
                except Exception as e:
                    print(f"[{self._get_timestamp_et()}] ERROR placing trailing stop: {e}")
        
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR checking profit target: {e}")
    
    async def close_all_positions(self, reason=""):
        """Close all positions and log final P&L"""
        try:
            print(f"\n[{self._get_timestamp_et()}] CLOSING ALL POSITIONS - {reason}")
            positions = self.trading_client.get_all_positions()
            
            for position in positions:
                if position.symbol in [LONG_TICKER, SHORT_TICKER]:
                    # Log final P&L before closing
                    final_pl = float(position.unrealized_pl)
                    final_pl_pct = float(position.unrealized_plpc) * 100
                    current_price = float(position.current_price)
                    qty = float(position.qty)
                    
                    print(f"[{self._get_timestamp_et()}] === FINAL TRADE SUMMARY ===")
                    print(f"[{self._get_timestamp_et()}] Symbol: {position.symbol}")
                    print(f"[{self._get_timestamp_et()}] Entry Price: ${self.entry_price:.2f}")
                    print(f"[{self._get_timestamp_et()}] Exit Price: ${current_price:.2f}")
                    print(f"[{self._get_timestamp_et()}] Shares: {int(qty)}")
                    print(f"[{self._get_timestamp_et()}] Final P&L: ${final_pl:.2f} ({final_pl_pct:+.2f}%)")
                    print(f"[{self._get_timestamp_et()}] ==========================")
                    
                    # Close the position
                    self.trading_client.close_position(position.symbol)
                    print(f"[{self._get_timestamp_et()}] Position closed successfully")
            
            # Cancel any pending orders
            try:
                self.trading_client.cancel_orders()
                print(f"[{self._get_timestamp_et()}] All pending orders canceled")
            except:
                pass
            
            self.position_entered = False
            self.position_side = None
            self.entry_price = None
            self.entry_ticker = None
            
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR closing positions: {e}")
    
    async def handle_nvda_bar(self, bar):
        """Handle incoming NVDA bar data (1-minute bars)"""
        try:
            current_time_et = self._get_current_time_et()
            current_time_cst = self._get_current_time_cst()
            bar_time = bar.timestamp.astimezone(TIMEZONE_ET).time()
            
            # Check for Golden Gap exit (2:00 PM CST)
            if current_time_cst >= GOLDEN_GAP_EXIT:
                if self.position_entered:
                    await self.close_all_positions(f"GOLDEN GAP EXIT at {self._get_timestamp_cst()}")
                print(f"[{self._get_timestamp_cst()}] Golden Gap exit time reached. Bot stopping.")
                await self.stream.stop_ws()
                return
            
            # Update 5-minute candle tracking
            bar_minute = bar_time.minute
            
            # Determine which 5-min candle this bar belongs to
            candle_group = bar_minute // 5
            candle_start_minute = candle_group * 5
            candle_key = (bar_time.hour, candle_start_minute)
            
            # If new 5-min candle, reset tracking
            if self.last_5min_candle_time != candle_key:
                # Check previous 5-min candle for breakout before resetting
                if (self.last_5min_candle_time is not None and 
                    self.current_5min_close is not None and 
                    self.orb_established and 
                    not self.position_entered and 
                    self.trades_today < MAX_TRADES_PER_DAY and
                    current_time_et >= TRADING_START):
                    
                    await self.check_breakout_entry()
                
                # Reset for new 5-min candle
                self.last_5min_candle_time = candle_key
                self.current_5min_high = float(bar.high)
                self.current_5min_low = float(bar.low)
                self.current_5min_close = float(bar.close)
            else:
                # Update current 5-min candle
                self.current_5min_high = max(self.current_5min_high, float(bar.high))
                self.current_5min_low = min(self.current_5min_low, float(bar.low))
                self.current_5min_close = float(bar.close)
            
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR in handle_nvda_bar: {e}")
    
    async def check_breakout_entry(self):
        """Check if 5-min candle closed above/below ORB"""
        try:
            # Check if already have a position
            if self.check_existing_position():
                print(f"[{self._get_timestamp_et()}] Position already exists. Skipping entry.")
                self.position_entered = True
                return
            
            # Long entry: 5-min close above ORB high
            if self.current_5min_close > self.orb_high:
                print(f"\n[{self._get_timestamp_et()}] LONG BREAKOUT DETECTED!")
                print(f"[{self._get_timestamp_et()}] 5-min Close: ${self.current_5min_close:.2f} > ORB High: ${self.orb_high:.2f}")
                await self.place_trade_with_stop(LONG_TICKER, OrderSide.BUY, self.current_5min_close)
            
            # Short entry: 5-min close below ORB low
            elif self.current_5min_close < self.orb_low:
                print(f"\n[{self._get_timestamp_et()}] SHORT BREAKOUT DETECTED!")
                print(f"[{self._get_timestamp_et()}] 5-min Close: ${self.current_5min_close:.2f} < ORB Low: ${self.orb_low:.2f}")
                await self.place_trade_with_stop(SHORT_TICKER, OrderSide.BUY, self.current_5min_close)
        
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR in check_breakout_entry: {e}")
    
    async def handle_nvdl_trade(self, data):
        """Handle incoming NVDL trade data - used for profit target and position monitoring"""
        try:
            current_time_et = self._get_current_time_et()
            current_time_cst = self._get_current_time_cst()
            self.nvdl_current_price = float(data.price)
            
            # Only process if we have a NVDL position
            if not self.position_entered or self.entry_ticker != LONG_TICKER:
                return
            
            # Check for Golden Gap exit
            if current_time_cst >= GOLDEN_GAP_EXIT:
                await self.close_all_positions(f"GOLDEN GAP EXIT at {self._get_timestamp_cst()}")
                print(f"[{self._get_timestamp_cst()}] Golden Gap exit time reached. Bot stopping.")
                await self.stream.stop_ws()
                return
            
            # Update highest price tracking
            if self.nvdl_current_price > self.highest_price_since_entry:
                self.highest_price_since_entry = self.nvdl_current_price
                if not self.profit_target_hit:
                    print(f"[{self._get_timestamp_et()}] New high for {LONG_TICKER}: ${self.highest_price_since_entry:.2f}")
            
            # Check profit target
            await self.check_profit_target(self.nvdl_current_price)
            
            # Periodic logging every 30 seconds
            if self.should_log_periodic_update():
                price_change = self.nvdl_current_price - self.entry_price
                pl = price_change * self.shares
                pl_pct = (price_change / self.entry_price) * 100
                print(f"[{self._get_timestamp_et()}] >>> {LONG_TICKER} High: ${self.highest_price_since_entry:.2f} | Current: ${self.nvdl_current_price:.2f} | P&L: ${pl:.2f} ({pl_pct:+.2f}%)")
        
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR in handle_nvdl_trade: {e}")
    
    async def handle_nvd_trade(self, data):
        """Handle incoming NVD trade data - used for profit target and position monitoring"""
        try:
            current_time_et = self._get_current_time_et()
            current_time_cst = self._get_current_time_cst()
            self.nvd_current_price = float(data.price)
            
            # Only process if we have an NVD position
            if not self.position_entered or self.entry_ticker != SHORT_TICKER:
                return
            
            # Check for Golden Gap exit
            if current_time_cst >= GOLDEN_GAP_EXIT:
                await self.close_all_positions(f"GOLDEN GAP EXIT at {self._get_timestamp_cst()}")
                print(f"[{self._get_timestamp_cst()}] Golden Gap exit time reached. Bot stopping.")
                await self.stream.stop_ws()
                return
            
            # Update lowest price tracking (for short positions, we track the lowest)
            if self.nvd_current_price < self.lowest_price_since_entry:
                self.lowest_price_since_entry = self.nvd_current_price
                if not self.profit_target_hit:
                    print(f"[{self._get_timestamp_et()}] New low for {SHORT_TICKER}: ${self.lowest_price_since_entry:.2f}")
            
            # Check profit target
            await self.check_profit_target(self.nvd_current_price)
            
            # Periodic logging every 30 seconds
            if self.should_log_periodic_update():
                # For short ETF, profit = entry - current (inverse)
                price_change = self.entry_price - self.nvd_current_price
                pl = price_change * self.shares
                pl_pct = (price_change / self.entry_price) * 100
                print(f"[{self._get_timestamp_et()}] >>> {SHORT_TICKER} Low: ${self.lowest_price_since_entry:.2f} | Current: ${self.nvd_current_price:.2f} | P&L: ${pl:.2f} ({pl_pct:+.2f}%)")
        
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR in handle_nvd_trade: {e}")
    
    async def run(self):
        """Main bot loop"""
        print(f"\n{'='*70}")
        print(f"NVDA 15-MIN OPENING RANGE BREAKOUT BOT STARTED")
        print(f"{'='*70}\n")
        
        # Wait for market to open
        await self.wait_for_market_open()
        
        # Establish opening range
        if not await self.establish_opening_range():
            print(f"[{self._get_timestamp_et()}] Failed to establish ORB. Exiting.")
            return
        
        print(f"\n[{self._get_timestamp_et()}] STRATEGY SUMMARY:")
        print(f"[{self._get_timestamp_et()}] Long Entry: NVDA 5-min close > ${self.orb_high:.2f} → Buy {LONG_TICKER}")
        print(f"[{self._get_timestamp_et()}] Short Entry: NVDA 5-min close < ${self.orb_low:.2f} → Buy {SHORT_TICKER}")
        print(f"[{self._get_timestamp_et()}] Max Trades: {MAX_TRADES_PER_DAY}")
        print(f"[{self._get_timestamp_et()}] Exit Strategy:")
        print(f"[{self._get_timestamp_et()}]   Stage 1: {HARD_STOP_PCT}% Hard Stop Loss")
        print(f"[{self._get_timestamp_et()}]   Stage 2: {PROFIT_TARGET_PCT}% Profit → {TRAILING_STOP_PCT}% Trailing Stop")
        print(f"[{self._get_timestamp_et()}]   Stage 3: Golden Gap Exit at 2:00 PM CST")
        print(f"[{self._get_timestamp_et()}] Monitoring NVDA 5-min candles...\n")
        
        # Subscribe to NVDA 1-minute bars (to track 5-min candles for entry signals)
        self.stream.subscribe_bars(self.handle_nvda_bar, MONITOR_TICKER)
        
        # Subscribe to NVDL and NVD trade streams (for real-time position monitoring)
        self.stream.subscribe_trades(self.handle_nvdl_trade, LONG_TICKER)
        self.stream.subscribe_trades(self.handle_nvd_trade, SHORT_TICKER)
        
        print(f"[{self._get_timestamp_et()}] Subscribed to {MONITOR_TICKER} live bar stream (entry signals)")
        print(f"[{self._get_timestamp_et()}] Subscribed to {LONG_TICKER} live trade stream (long position monitoring)")
        print(f"[{self._get_timestamp_et()}] Subscribed to {SHORT_TICKER} live trade stream (short position monitoring)")
        print(f"[{self._get_timestamp_et()}] Waiting for breakout signals...\n")
        
        # Run the stream
        await self.stream.run()


async def main():
    bot = NVDAOpeningRangeBot()
    await bot.run()


if __name__ == "__main__":
    # Handle both Railway and local environments
    try:
        # Try the standard approach (works locally)
        asyncio.run(main())
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            # Railway environment - event loop already exists
            # Get the existing loop and run the coroutine
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        else:
            raise
