"""
NVDA 15-Minute Opening Range Breakout (ORB) Strategy
- Monitors NVDA for 15-min ORB (9:30-9:45 AM ET)
- Trades NVDL (2x Long) or NVD (2x Short) based on 5-min candle closes
- Position sizing: 1.5% move = $300 loss on $20k account
- Dual-stage exit: 1.5% hard stop -> 3% profit triggers 1% trailing stop
- Hard exit at 2:00 PM CST (Golden Gap for MSOS bot at 2:15 PM)
- Maximum one trade per day
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
    StopLossRequest,
    TrailingStopOrderRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
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

# Startup coordination
RESTART_TRACKER_FILE = "/tmp/nvda_bot_restart_count.txt"


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
        self.orb_tracking = False  # True when we're tracking ORB (9:30-9:45)
        self.position_entered = False
        self.position_side = None  # 'long' or 'short'
        self.entry_price = None
        self.entry_ticker = None
        self.active_ticker = None  # Track which ticker we're monitoring (NVDL or NVD)
        self.shares = 0
        self.stop_loss_order_id = None
        self.profit_target_hit = False
        self.trades_today = 0
        
        # Track 5-minute candles (after ORB)
        self.current_5min_candle = {}  # Stores open, high, low, close for current 5-min candle
        self.last_5min_start_time = None
        
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
        """Check if market is open, exit if not (Railway will restart)"""
        now_et = datetime.now(TIMEZONE_ET)
        
        # Check if weekend
        if now_et.weekday() >= 5:  # Saturday or Sunday
            days_until_monday = (7 - now_et.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 1
            
            next_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0) + timedelta(days=days_until_monday)
            
            print(f"[{self._get_timestamp_et()}] Market closed (weekend)")
            print(f"[{self._get_timestamp_et()}] Next open: Monday {next_open.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"[{self._get_timestamp_et()}] Exiting - Railway will restart closer to market open")
            await asyncio.sleep(30)
            return False
        
        # Check if before market open today
        market_open_time = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        
        if now_et < market_open_time:
            wait_seconds = (market_open_time - now_et).total_seconds()
            print(f"[{self._get_timestamp_et()}] Market opens at 9:30 AM ET")
            print(f"[{self._get_timestamp_et()}] {wait_seconds:.0f} seconds until open")
            
            # If more than 5 minutes away, exit and let Railway restart
            if wait_seconds > 300:
                print(f"[{self._get_timestamp_et()}] Exiting - Railway will restart closer to market open")
                await asyncio.sleep(30)
                return False
            else:
                # Less than 5 minutes - wait for it
                print(f"[{self._get_timestamp_et()}] Waiting {wait_seconds:.0f} seconds for market open...")
                await asyncio.sleep(wait_seconds)
                print(f"[{self._get_timestamp_et()}] Market is open - ready to trade")
                return True
        
        # Market is open!
        print(f"[{self._get_timestamp_et()}] Market is open - ready to trade")
        return True
    
    async def handle_nvda_bar(self, bar):
        """Handle incoming 1-minute NVDA bars for ORB tracking and 5-min aggregation"""
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
            
            # Phase 1: Track ORB during 9:30-9:45 AM
            if self.orb_tracking and not self.orb_established:
                # Update running high/low
                bar_high = float(bar.high)
                bar_low = float(bar.low)
                
                if self.orb_high is None:
                    self.orb_high = bar_high
                    self.orb_low = bar_low
                else:
                    self.orb_high = max(self.orb_high, bar_high)
                    self.orb_low = min(self.orb_low, bar_low)
                
                # Check if ORB period is complete (at or after 9:45 AM)
                if bar_time >= ORB_END:
                    self.orb_established = True
                    self.orb_tracking = False
                    
                    print(f"\n[{self._get_timestamp_et()}] ===== OPENING RANGE ESTABLISHED =====")
                    print(f"[{self._get_timestamp_et()}] Time: 9:30-9:45 AM ET")
                    print(f"[{self._get_timestamp_et()}] ORB High: ${self.orb_high:.2f}")
                    print(f"[{self._get_timestamp_et()}] ORB Low: ${self.orb_low:.2f}")
                    print(f"[{self._get_timestamp_et()}] ORB Range: ${self.orb_high - self.orb_low:.2f}")
                    print(f"[{self._get_timestamp_et()}] =====================================\n")
                    print(f"[{self._get_timestamp_et()}] Now monitoring 5-minute candles for breakouts...\n")
                return
            
            # Phase 2: After ORB, aggregate into 5-min candles
            if self.orb_established and not self.position_entered and self.trades_today < MAX_TRADES_PER_DAY:
                await self.aggregate_5min_candle(bar)
            
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR in handle_nvda_bar: {e}")
    
    def calculate_position_size(self, entry_price):
        """
        Calculate shares for $20K position size
        - Target position: $20,000
        - ETF is 2x leveraged
        
        Formula: shares = $20,000 / entry_price
        """
        leverage = 2.0
        
        # Calculate shares for $20K position
        shares = int(ACCOUNT_SIZE / entry_price)
        
        notional_value = shares * entry_price
        # With 1.5% stop on 2x leveraged ETF, actual dollar risk will be:
        # shares × entry_price × 1.5% × 2 = total risk
        max_loss = shares * entry_price * (HARD_STOP_PCT / 100) * leverage
        max_loss_pct = (max_loss / ACCOUNT_SIZE) * 100
        
        print(f"[{self._get_timestamp_et()}] Position Sizing:")
        print(f"[{self._get_timestamp_et()}]   Entry Price: ${entry_price:.2f}")
        print(f"[{self._get_timestamp_et()}]   Shares: {shares}")
        print(f"[{self._get_timestamp_et()}]   Notional Value: ${notional_value:.2f}")
        print(f"[{self._get_timestamp_et()}]   Expected Max Loss: ${max_loss:.2f} ({max_loss_pct:.2f}% of position)")
        
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
    
    async def get_latest_price(self, ticker: str):
        """Get the latest quote price for a ticker"""
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            latest_quote = self.data_client.get_stock_latest_quote(request)
            
            if ticker in latest_quote:
                ask_price = float(latest_quote[ticker].ask_price)
                bid_price = float(latest_quote[ticker].bid_price)
                mid_price = (ask_price + bid_price) / 2
                
                print(f"[{self._get_timestamp_et()}] {ticker} Latest Quote - Bid: ${bid_price:.2f}, Ask: ${ask_price:.2f}, Mid: ${mid_price:.2f}")
                return mid_price
            else:
                print(f"[{self._get_timestamp_et()}] ERROR: No quote data for {ticker}")
                return None
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR getting latest price for {ticker}: {e}")
            return None
    
    async def place_trade_with_stop(self, ticker: str, side: OrderSide, nvda_signal_price: float):
        """Place trade with bracket order (entry + stop loss)"""
        try:
            print(f"\n[{self._get_timestamp_et()}] {'LONG' if side == OrderSide.BUY else 'SHORT'} SIGNAL DETECTED")
            print(f"[{self._get_timestamp_et()}] NVDA Signal Price: ${nvda_signal_price:.2f}")
            
            # Get the actual current price of the ETF we're trading
            etf_price = await self.get_latest_price(ticker)
            if etf_price is None:
                print(f"[{self._get_timestamp_et()}] ERROR: Could not get price for {ticker}. Order cancelled.")
                return False
            
            # Calculate position size based on ETF price (not NVDA price!)
            shares = self.calculate_position_size(etf_price)
            
            if shares <= 0:
                print(f"[{self._get_timestamp_et()}] ERROR: Invalid position size ({shares} shares)")
                return False
            
            # Calculate stop loss price based on ETF price
            # IMPORTANT: Must round to 2 decimals - Alpaca requires penny increments for stocks > $1
            if side == OrderSide.BUY:
                stop_price = round(etf_price * (1 - HARD_STOP_PCT / 100), 2)
            else:
                stop_price = round(etf_price * (1 + HARD_STOP_PCT / 100), 2)
            
            print(f"\n[{self._get_timestamp_et()}] PLACING {'LONG' if side == OrderSide.BUY else 'SHORT'} ORDER")
            print(f"[{self._get_timestamp_et()}] Ticker: {ticker}")
            print(f"[{self._get_timestamp_et()}] Shares: {shares}")
            print(f"[{self._get_timestamp_et()}] Expected Entry: ${etf_price:.2f}")
            print(f"[{self._get_timestamp_et()}] Stop Loss: ${stop_price:.2f} ({HARD_STOP_PCT}%)")
            
            # Submit market order with stop loss
            # Using OTO (One-Triggers-Other) instead of BRACKET since we only have stop loss, no take profit
            order_data = MarketOrderRequest(
                symbol=ticker,
                qty=shares,
                side=side,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.OTO,
                stop_loss=StopLossRequest(stop_price=stop_price)
            )
            
            order = self.trading_client.submit_order(order_data)
            print(f"[{self._get_timestamp_et()}] Order submitted - Order ID: {order.id}")
            
            # Wait for order to fill and verify
            await asyncio.sleep(3)
            
            # Check order status
            filled_order = self.trading_client.get_order_by_id(order.id)
            
            if filled_order.status == 'filled':
                actual_fill_price = float(filled_order.filled_avg_price)
                print(f"[{self._get_timestamp_et()}] SUCCESS: ORDER FILLED at ${actual_fill_price:.2f}")
                
                # NOW set position state (only after confirming fill)
                self.position_entered = True
                self.position_side = 'long' if side == OrderSide.BUY else 'short'
                self.entry_ticker = ticker
                self.entry_price = actual_fill_price
                self.shares = shares
                self.trades_today += 1
                
                # Log exit strategy clearly
                log_and_flush(f"\n[{self._get_timestamp_et()}] ===== EXIT STRATEGY ACTIVE =====")
                log_and_flush(f"[{self._get_timestamp_et()}] 1. HARD STOP @ ${stop_price:.2f} (-{HARD_STOP_PCT}%) - Set on Alpaca, executes automatically")
                log_and_flush(f"[{self._get_timestamp_et()}] 2. PROFIT TARGET @ ${actual_fill_price * (1 + PROFIT_TARGET_PCT / 100):.2f} (+{PROFIT_TARGET_PCT}%) - Upgrades to {TRAILING_STOP_PCT}% trailing stop")
                log_and_flush(f"[{self._get_timestamp_et()}] 3. GOLDEN GAP EXIT @ 2:00 PM CST - Forced exit regardless of P&L")
                log_and_flush(f"[{self._get_timestamp_et()}] Monitoring position for stop hits and profit target...")
                log_and_flush(f"[{self._get_timestamp_et()}] =================================\n")
                
                # Initialize price tracking for trailing stop
                self.highest_price_since_entry = actual_fill_price
                self.lowest_price_since_entry = actual_fill_price
                
                # Get stop loss order ID
                await self.get_child_orders(order.id)
                
                return True
            else:
                print(f"[{self._get_timestamp_et()}] FAILED: ORDER NOT FILLED - Status: {filled_order.status}")
                print(f"[{self._get_timestamp_et()}] Reason: {filled_order.status}")
                
                # Cancel the order if it's still pending
                try:
                    self.trading_client.cancel_order_by_id(order.id)
                    print(f"[{self._get_timestamp_et()}] Order cancelled")
                except:
                    pass
                
                return False
            
        except Exception as e:
            error_msg = str(e)
            log_and_flush(f"[{self._get_timestamp_et()}] !!!!! ERROR placing order: {error_msg} !!!!!")
            log_and_flush(f"[{self._get_timestamp_et()}] Error type: {type(e).__name__}")
            log_and_flush(f"[{self._get_timestamp_et()}] Ticker: {ticker}, Shares: {shares}, Stop Price: {stop_price}")
            
            # Check if it's a connection limit issue during order placement
            if "connection limit" in error_msg.lower() or "429" in error_msg:
                log_and_flush(f"[{self._get_timestamp_et()}] CONNECTION LIMIT ERROR during order placement")
                log_and_flush(f"[{self._get_timestamp_et()}] This means another bot is connected to Alpaca")
                log_and_flush(f"[{self._get_timestamp_et()}] Check Railway dashboard for multiple replicas")
            
            log_and_flush(f"[{self._get_timestamp_et()}] Position NOT entered due to error")
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
    
    async def aggregate_5min_candle(self, bar):
        """Aggregate 1-minute bars into 5-minute candles"""
        try:
            bar_time = bar.timestamp.astimezone(TIMEZONE_ET)
            
            # Determine which 5-min period this bar belongs to
            minute = bar_time.minute
            period_start_minute = (minute // 5) * 5
            period_start_time = bar_time.replace(minute=period_start_minute, second=0, microsecond=0)
            
            # If this is a new 5-min period, check previous candle for signals
            if self.last_5min_start_time is not None and period_start_time != self.last_5min_start_time:
                # Previous 5-min candle is complete - check for breakout
                await self.check_5min_breakout()
                
                # Reset for new candle
                self.current_5min_candle = {
                    'open': float(bar.open),
                    'high': float(bar.high),
                    'low': float(bar.low),
                    'close': float(bar.close)
                }
                self.last_5min_start_time = period_start_time
            elif self.last_5min_start_time is None:
                # First bar after ORB
                self.current_5min_candle = {
                    'open': float(bar.open),
                    'high': float(bar.high),
                    'low': float(bar.low),
                    'close': float(bar.close)
                }
                self.last_5min_start_time = period_start_time
            else:
                # Same 5-min period - update candle
                self.current_5min_candle['high'] = max(self.current_5min_candle['high'], float(bar.high))
                self.current_5min_candle['low'] = min(self.current_5min_candle['low'], float(bar.low))
                self.current_5min_candle['close'] = float(bar.close)
        
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR in aggregate_5min_candle: {e}")
    
    async def check_5min_breakout(self):
        """Check if completed 5-min candle signals a breakout"""
        try:
            if not self.current_5min_candle:
                return
            
            candle_open = self.current_5min_candle['open']
            candle_close = self.current_5min_candle['close']
            candle_high = self.current_5min_candle['high']
            candle_low = self.current_5min_candle['low']
            
            print(f"[{self._get_timestamp_et()}] 5-min Candle Complete: O=${candle_open:.2f} H=${candle_high:.2f} L=${candle_low:.2f} C=${candle_close:.2f}")
            
            # Check if candle BODY is entirely above ORB High (LONG)
            # Both open AND close must be above ORB high
            if candle_open > self.orb_high and candle_close > self.orb_high:
                print(f"\n[{self._get_timestamp_et()}] === LONG BREAKOUT DETECTED ===")
                print(f"[{self._get_timestamp_et()}] Candle Body: Open=${candle_open:.2f}, Close=${candle_close:.2f}")
                print(f"[{self._get_timestamp_et()}] ORB High: ${self.orb_high:.2f}")
                print(f"[{self._get_timestamp_et()}] Body entirely above ORB High - LONG signal confirmed!")
                
                # Check for existing position before entering
                if self.check_existing_position():
                    print(f"[{self._get_timestamp_et()}] Position already exists. Skipping entry.")
                    self.position_entered = True
                    return
                
                await self.place_trade_with_stop(LONG_TICKER, OrderSide.BUY, candle_close)
            
            # Check if candle BODY is entirely below ORB Low (SHORT)
            # Both open AND close must be below ORB low
            elif candle_open < self.orb_low and candle_close < self.orb_low:
                print(f"\n[{self._get_timestamp_et()}] === SHORT BREAKOUT DETECTED ===")
                print(f"[{self._get_timestamp_et()}] Candle Body: Open=${candle_open:.2f}, Close=${candle_close:.2f}")
                print(f"[{self._get_timestamp_et()}] ORB Low: ${self.orb_low:.2f}")
                print(f"[{self._get_timestamp_et()}] Body entirely below ORB Low - SHORT signal confirmed!")
                
                # Check for existing position before entering
                if self.check_existing_position():
                    print(f"[{self._get_timestamp_et()}] Position already exists. Skipping entry.")
                    self.position_entered = True
                    return
                
                await self.place_trade_with_stop(SHORT_TICKER, OrderSide.BUY, candle_close)
            else:
                # No breakout - just log ORB reference
                print(f"[{self._get_timestamp_et()}] No breakout (ORB High: ${self.orb_high:.2f}, ORB Low: ${self.orb_low:.2f})")
        
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR in check_5min_breakout: {e}")
    
    
    async def handle_nvdl_trade(self, data):
        """Handle incoming NVDL trade data - used for profit target and position monitoring"""
        try:
            current_time_et = self._get_current_time_et()
            current_time_cst = self._get_current_time_cst()
            self.nvdl_current_price = float(data.price)
            
            # Only process if we have a NVDL position
            if not self.position_entered or self.entry_ticker != LONG_TICKER:
                return
            
            # Check if position still exists (stop loss may have been hit by Alpaca)
            try:
                position = self.trading_client.get_open_position(LONG_TICKER)
                if position is None:
                    expected_stop = round(self.entry_price * (1 - HARD_STOP_PCT / 100), 2)
                    log_and_flush(f"\n[{self._get_timestamp_et()}] !!!!! STOP LOSS HIT BY ALPACA !!!!!")
                    log_and_flush(f"[{self._get_timestamp_et()}] Position closed automatically at stop price")
                    log_and_flush(f"[{self._get_timestamp_et()}] Entry: ${self.entry_price:.2f} → Stop: ~${expected_stop:.2f}")
                    log_and_flush(f"[{self._get_timestamp_et()}] Estimated Loss: ~${(expected_stop - self.entry_price) * self.shares:.2f} (-{HARD_STOP_PCT}%)")
                    log_and_flush(f"[{self._get_timestamp_et()}] Check Alpaca dashboard for exact exit price")
                    self.position_entered = False
                    self.position_side = None
                    return
            except Exception:
                log_and_flush(f"\n[{self._get_timestamp_et()}] !!!!! POSITION CLOSED !!!!!")
                log_and_flush(f"[{self._get_timestamp_et()}] Position no longer exists - likely stop loss triggered")
                log_and_flush(f"[{self._get_timestamp_et()}] Check Alpaca dashboard for final exit details")
                self.position_entered = False
                self.position_side = None
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
            
            # Check if position still exists (stop loss may have been hit by Alpaca)
            try:
                position = self.trading_client.get_open_position(SHORT_TICKER)
                if position is None:
                    expected_stop = round(self.entry_price * (1 - HARD_STOP_PCT / 100), 2)
                    log_and_flush(f"\n[{self._get_timestamp_et()}] !!!!! STOP LOSS HIT BY ALPACA !!!!!")
                    log_and_flush(f"[{self._get_timestamp_et()}] Position closed automatically at stop price")
                    log_and_flush(f"[{self._get_timestamp_et()}] Entry: ${self.entry_price:.2f} → Stop: ~${expected_stop:.2f}")
                    log_and_flush(f"[{self._get_timestamp_et()}] Estimated Loss: ~${(expected_stop - self.entry_price) * self.shares:.2f} (-{HARD_STOP_PCT}%)")
                    log_and_flush(f"[{self._get_timestamp_et()}] Check Alpaca dashboard for exact exit price")
                    self.position_entered = False
                    self.position_side = None
                    return
            except Exception:
                log_and_flush(f"\n[{self._get_timestamp_et()}] !!!!! POSITION CLOSED !!!!!")
                log_and_flush(f"[{self._get_timestamp_et()}] Position no longer exists - likely stop loss triggered")
                log_and_flush(f"[{self._get_timestamp_et()}] Check Alpaca dashboard for final exit details")
                self.position_entered = False
                self.position_side = None
                return
            
            # Check for Golden Gap exit
            if current_time_cst >= GOLDEN_GAP_EXIT:
                await self.close_all_positions(f"GOLDEN GAP EXIT at {self._get_timestamp_cst()}")
                print(f"[{self._get_timestamp_cst()}] Golden Gap exit time reached. Bot stopping.")
                await self.stream.stop_ws()
                return
            
            # Update lowest price tracking (for long NVD positions, we still track lowest as reference)
            if self.nvd_current_price < self.lowest_price_since_entry:
                self.lowest_price_since_entry = self.nvd_current_price
                if not self.profit_target_hit:
                    print(f"[{self._get_timestamp_et()}] New low for {SHORT_TICKER}: ${self.lowest_price_since_entry:.2f}")
            
            # Check profit target
            await self.check_profit_target(self.nvd_current_price)
            
            # Periodic logging every 30 seconds
            if self.should_log_periodic_update():
                # NVD is a LONG position (we BUY the inverse ETF)
                # P&L calculation is the same as any long: (current - entry) * shares
                price_change = self.nvd_current_price - self.entry_price
                pl = price_change * self.shares
                pl_pct = (price_change / self.entry_price) * 100
                print(f"[{self._get_timestamp_et()}] >>> {SHORT_TICKER} Low: ${self.lowest_price_since_entry:.2f} | Current: ${self.nvd_current_price:.2f} | P&L: ${pl:.2f} ({pl_pct:+.2f}%)")
        
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR in handle_nvd_trade: {e}")
    
    async def run(self):
        """Main bot loop"""
        log_and_flush(f"\n{'='*70}")
        log_and_flush(f"NVDA 15-MIN OPENING RANGE BREAKOUT BOT STARTED")
        log_and_flush(f"{'='*70}\n")
        
        # STEP 1: Implement exponential backoff if we've been restarting repeatedly
        attempt_num = await handle_connection_limit_backoff()
        if attempt_num > 5:
            log_and_flush(f"[ERROR] Too many restart attempts ({attempt_num})")
            log_and_flush(f"[ERROR] Possible causes:")
            log_and_flush(f"[ERROR]   - Multiple Railway replicas running")
            log_and_flush(f"[ERROR]   - Another bot holding the connection")
            log_and_flush(f"[ERROR]   - Alpaca API issues")
            log_and_flush(f"[INFO] Exiting - check Railway dashboard for multiple replicas")
            await asyncio.sleep(60)
            return
        
        # STEP 2: Check if we should run right now (prevent connecting to websockets when not needed)
        now_et = datetime.now(TIMEZONE_ET)
        now_cst = datetime.now(pytz.timezone('America/Chicago'))
        current_time_cst = now_cst.time()
        
        # CRITICAL: Don't connect to Alpaca if MSOS bot should be running (2:00 PM - 4:00 PM CST)
        # This prevents connection limit exceeded errors
        if time(14, 0) <= current_time_cst <= time(16, 0):
            log_and_flush(f"[{self._get_timestamp_et()}] Current time: {now_cst.strftime('%H:%M:%S %Z')}")
            log_and_flush(f"[{self._get_timestamp_et()}] NVDA bot window closed (2:00 PM CST - next day)")
            log_and_flush(f"[{self._get_timestamp_et()}] MSOS bot time slot - exiting to avoid connection conflict")
            log_and_flush(f"[{self._get_timestamp_et()}] Railway will restart this bot and check again")
            await asyncio.sleep(30)
            return
        
        # STEP 3: Wait for market to open
        if not await self.wait_for_market_open():
            return  # Exit if market not open
        
        # STEP 4: Test Alpaca API connection BEFORE subscribing to websockets
        if not await test_alpaca_connection(self.trading_client):
            log_and_flush(f"[ERROR] Cannot connect to Alpaca API - exiting")
            await asyncio.sleep(30)
            return
        
        # Check for existing positions (in case of bot restart)
        print(f"\n[{self._get_timestamp_et()}] Checking for existing positions...")
        if self.check_existing_position():
            print(f"[{self._get_timestamp_et()}] WARNING: Existing position found at startup")
            print(f"[{self._get_timestamp_et()}] Bot will monitor existing position but not enter new trades today")
            self.position_entered = True
            self.trades_today = MAX_TRADES_PER_DAY
        else:
            print(f"[{self._get_timestamp_et()}] No existing positions found - ready to trade")
        
        print(f"\n[{self._get_timestamp_et()}] STRATEGY CONFIGURATION:")
        print(f"[{self._get_timestamp_et()}] Phase 1 (9:30-9:45 AM): Track 15-min ORB")
        print(f"[{self._get_timestamp_et()}] Phase 2 (After 9:45 AM): Monitor 5-min candles for breakouts")
        print(f"[{self._get_timestamp_et()}] Long Entry: 5-min body entirely above ORB High -> Buy {LONG_TICKER}")
        print(f"[{self._get_timestamp_et()}] Short Entry: 5-min body entirely below ORB Low -> Buy {SHORT_TICKER}")
        print(f"[{self._get_timestamp_et()}] Max Trades: {MAX_TRADES_PER_DAY}")
        print(f"[{self._get_timestamp_et()}] Exit Strategy:")
        print(f"[{self._get_timestamp_et()}]   Stage 1: {HARD_STOP_PCT}% Hard Stop Loss")
        print(f"[{self._get_timestamp_et()}]   Stage 2: {PROFIT_TARGET_PCT}% Profit -> {TRAILING_STOP_PCT}% Trailing Stop")
        print(f"[{self._get_timestamp_et()}]   Stage 3: Golden Gap Exit at 2:00 PM CST\n")
        
        # Mark that we're tracking ORB
        self.orb_tracking = True
        
        # Subscribe to 1-minute bars for NVDA
        # - During 9:30-9:45: Tracks high/low to build ORB
        # - After 9:45: Aggregates into 5-min candles for breakout signals
        print(f"[{self._get_timestamp_et()}] Subscribing to {MONITOR_TICKER} live bars...")
        self.stream.subscribe_bars(self.handle_nvda_bar, MONITOR_TICKER)
        
        # Subscribe to NVDL and NVD trade streams (for real-time position monitoring)
        self.stream.subscribe_trades(self.handle_nvdl_trade, LONG_TICKER)
        self.stream.subscribe_trades(self.handle_nvd_trade, SHORT_TICKER)
        
        print(f"[{self._get_timestamp_et()}] Subscribed to {MONITOR_TICKER} bars (ORB + entry signals)")
        print(f"[{self._get_timestamp_et()}] Subscribed to {LONG_TICKER} trades (position monitoring)")
        print(f"[{self._get_timestamp_et()}] Subscribed to {SHORT_TICKER} trades (position monitoring)")
        print(f"[{self._get_timestamp_et()}] Tracking 9:30-9:45 AM opening range...\n")
        
        # Run the stream - use _run_forever() directly since we already have an event loop
        # The stream.run() method calls asyncio.run() which fails when a loop is already running
        try:
            await self.stream._run_forever()
        except ValueError as e:
            if "connection limit exceeded" in str(e):
                log_and_flush(f"\n[{self._get_timestamp_et()}] ERROR: Connection limit exceeded")
                log_and_flush(f"[{self._get_timestamp_et()}] This means another bot instance is using the Alpaca connection")
                log_and_flush(f"[{self._get_timestamp_et()}] Possible causes:")
                log_and_flush(f"[{self._get_timestamp_et()}]   1. Railway running multiple replicas of this service")
                log_and_flush(f"[{self._get_timestamp_et()}]   2. MSOS bot still connected (should have exited)")
                log_and_flush(f"[{self._get_timestamp_et()}]   3. Old deployment still running or websocket not properly closed")
                log_and_flush(f"[{self._get_timestamp_et()}] Exiting - Railway will restart in 30 seconds")
                await asyncio.sleep(30)
                return
            else:
                raise
        finally:
            # CRITICAL: Always close the websocket stream when exiting
            # This prevents orphaned connections that block future deployments
            try:
                log_and_flush(f"[{self._get_timestamp_et()}] Closing websocket connection...")
                await self.stream.close()
                log_and_flush(f"[{self._get_timestamp_et()}] Websocket closed successfully")
            except Exception as e:
                log_and_flush(f"[{self._get_timestamp_et()}] Error closing websocket: {e}")


async def main():
    # CRITICAL: Check time BEFORE creating bot to avoid websocket connection race condition
    # When Railway deploys both bots simultaneously, they both try to connect at once
    # This check prevents NVDA from even attempting connection during MSOS time window
    now_cst = datetime.now(pytz.timezone('America/Chicago'))
    current_time_cst = now_cst.time()
    
    # NVDA bot should NOT run between 2:00 PM - 4:00 PM CST (MSOS time)
    if time(14, 0) <= current_time_cst <= time(16, 0):
        log_and_flush(f"[{now_cst.strftime('%Y-%m-%d %H:%M:%S %Z')}] NVDA bot window closed (2:00 PM CST - next day)")
        log_and_flush(f"[{now_cst.strftime('%Y-%m-%d %H:%M:%S %Z')}] MSOS bot time slot - exiting WITHOUT connecting to Alpaca")
        log_and_flush(f"[{now_cst.strftime('%Y-%m-%d %H:%M:%S %Z')}] Railway will restart this bot and check again")
        await asyncio.sleep(30)
        return
    
    # Time check passed - safe to create bot and connect
    bot = NVDAOpeningRangeBot()
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
