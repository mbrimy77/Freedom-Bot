"""
NVDA 15-Minute Opening Range Breakout (ORB) Strategy
- Monitors NVDA for 15-min ORB (9:30-9:45 AM ET)
- Trades NVDL (2x Long) or NVD (2x Short) based on 5-min candle closes
- Position sizing: 1.5% move = $300 loss on $20k account
- Dual-stage exit: 1.5% hard stop -> 3% profit triggers 1% trailing stop
- Hard exit at 2:30 PM CST / 3:30 PM ET
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
    StopOrderRequest,
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
TRAILING_UPGRADE_RETRY_DELAY_SECONDS = 30
ORDER_STATE_POLL_SECONDS = 0.5
ORDER_STATE_TIMEOUT_SECONDS = 8

# Time windows (ET = Eastern Time, CST = Central Time)
ORB_START = time(9, 30)        # 9:30 AM ET (ORB start)
ORB_END = time(9, 45)          # 9:45 AM ET (ORB end)
TRADING_START = time(9, 45)    # 9:45 AM ET (start monitoring for breakouts)
END_OF_DAY_EXIT = time(14, 30)  # 2:30 PM CST / 3:30 PM ET (end of trading day)
PREMARKET_WAKE_ET = time(9, 25)  # Wake a few minutes before the opening bell
END_OF_DAY_EXIT_ET = time(15, 30)  # 3:30 PM ET

TIMEZONE_ET = pytz.timezone('America/New_York')
TIMEZONE_CST = pytz.timezone('America/Chicago')

# Startup coordination
RESTART_TRACKER_FILE = "/tmp/nvda_bot_restart_count.txt"
CONNECTION_LOCK_FILE = "/tmp/nvda_bot_connection.lock"


def log_and_flush(message):
    """Print and immediately flush to ensure logs appear in Railway"""
    print(message, flush=True)


def is_missing_position_error(error):
    """
    Alpaca raises when a position is not found. Distinguish that case from
    transient API/network issues so we don't falsely assume a live position
    has already been closed.
    """
    message = str(error).lower()
    return (
        "position does not exist" in message
        or "position not found" in message
        or "404" in message
    )


def get_next_session_start_et(now_et):
    """
    Return the next ET datetime when the bot should wake up and prepare to trade.
    Returns None when we are already inside the active startup/trading window.
    """
    target_date = now_et.date()

    if now_et.weekday() >= 5:
        days_until_monday = (7 - now_et.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 1
        target_date += timedelta(days=days_until_monday)
    elif now_et.time() >= END_OF_DAY_EXIT_ET:
        target_date += timedelta(days=1)
    elif now_et.time() < PREMARKET_WAKE_ET:
        pass
    else:
        return None

    while target_date.weekday() >= 5:
        target_date += timedelta(days=1)

    return TIMEZONE_ET.localize(datetime.combine(target_date, PREMARKET_WAKE_ET))


async def wait_until_session_start():
    """
    Keep the worker alive outside trading hours instead of exiting and hoping
    the platform restarts us later.
    """
    while True:
        now_et = datetime.now(TIMEZONE_ET)
        next_start = get_next_session_start_et(now_et)

        if next_start is None:
            return

        wait_seconds = max(1, int((next_start - now_et).total_seconds()))
        log_and_flush(
            f"[{now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}] Outside trading window. "
            f"Sleeping until {next_start.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        await asyncio.sleep(wait_seconds)


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


async def acquire_connection_lock():
    """
    Attempt to acquire a connection lock to prevent multiple instances from connecting.
    Returns True if lock acquired, False otherwise.
    """
    lock_path = Path(CONNECTION_LOCK_FILE)
    
    try:
        # Check if lock exists
        if lock_path.exists():
            content = lock_path.read_text().strip()
            if content:
                lock_time = float(content)
                age = datetime.now().timestamp() - lock_time
                
                # If lock is older than 10 minutes, assume it's stale and take it
                if age > 600:
                    log_and_flush(f"[INFO] Found stale lock ({age:.0f}s old) - cleaning up")
                    lock_path.write_text(str(datetime.now().timestamp()))
                    return True
                else:
                    log_and_flush(f"[ERROR] Another instance holds the connection lock ({age:.0f}s ago)")
                    log_and_flush(f"[ERROR] This means another bot is already connected to Alpaca")
                    log_and_flush(f"[ERROR] Railway may be running multiple replicas")
                    log_and_flush(f"[ERROR] Check Railway dashboard and set replicas to 1")
                    return False
        
        # No lock exists - create one
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(str(datetime.now().timestamp()))
        log_and_flush("[INFO] Connection lock acquired")
        return True
        
    except Exception as e:
        log_and_flush(f"[WARNING] Connection lock error: {e}")
        # If we can't manage locks, allow the connection (fail open)
        return True


def release_connection_lock():
    """Release the connection lock"""
    try:
        lock_path = Path(CONNECTION_LOCK_FILE)
        if lock_path.exists():
            lock_path.unlink()
            log_and_flush("[INFO] Connection lock released")
    except Exception as e:
        log_and_flush(f"[WARNING] Error releasing lock: {e}")


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
        self.trailing_upgrade_in_progress = False
        self.trailing_upgrade_retry_after = None
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
        """Wait until market open instead of exiting the worker."""
        now_et = datetime.now(TIMEZONE_ET)
        
        # Check if weekend
        if now_et.weekday() >= 5:  # Saturday or Sunday
            days_until_monday = (7 - now_et.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 1
            
            next_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0) + timedelta(days=days_until_monday)
            
            print(f"[{self._get_timestamp_et()}] Market closed (weekend)")
            print(f"[{self._get_timestamp_et()}] Next open: Monday {next_open.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"[{self._get_timestamp_et()}] Waiting for next market open...")
            await asyncio.sleep((next_open - now_et).total_seconds())
            print(f"[{self._get_timestamp_et()}] Market is open - ready to trade")
            return True
        
        # Check if before market open today
        market_open_time = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
        
        if now_et < market_open_time:
            wait_seconds = (market_open_time - now_et).total_seconds()
            print(f"[{self._get_timestamp_et()}] Market opens at 9:30 AM ET")
            print(f"[{self._get_timestamp_et()}] {wait_seconds:.0f} seconds until open")

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
            
            # Check for end of day exit (2:30 PM CST)
            if current_time_cst >= END_OF_DAY_EXIT:
                if self.position_entered:
                    await self.close_all_positions(f"END OF DAY EXIT at {self._get_timestamp_cst()}")
                print(f"[{self._get_timestamp_cst()}] End of trading day reached. Bot stopping.")
                await self.stream.stop_ws()
                return
            
            # Phase 1: Track ORB during 9:30-9:45 AM
            if self.orb_tracking and not self.orb_established:
                # CRITICAL: Check if ORB period is complete BEFORE processing this bar
                # This ensures we only include bars from 9:30-9:44 (15 minutes exactly)
                if bar_time >= ORB_END:
                    self.orb_established = True
                    self.orb_tracking = False
                    
                    # Verify we have valid ORB data
                    if self.orb_high is None or self.orb_low is None:
                        print(f"\n[{self._get_timestamp_et()}] ERROR: No bars received during ORB period!")
                        print(f"[{self._get_timestamp_et()}] Cannot establish Opening Range - no trading today")
                        print(f"[{self._get_timestamp_et()}] This usually means Alpaca websocket had connection issues")
                        self.trades_today = MAX_TRADES_PER_DAY  # Prevent trading
                        return
                    
                    print(f"\n[{self._get_timestamp_et()}] ===== OPENING RANGE ESTABLISHED =====")
                    print(f"[{self._get_timestamp_et()}] Time: 9:30-9:45 AM ET (15 minutes)")
                    print(f"[{self._get_timestamp_et()}] ORB High: ${self.orb_high:.2f}")
                    print(f"[{self._get_timestamp_et()}] ORB Low: ${self.orb_low:.2f}")
                    print(f"[{self._get_timestamp_et()}] ORB Range: ${self.orb_high - self.orb_low:.2f}")
                    print(f"[{self._get_timestamp_et()}] =====================================\n")
                    print(f"[{self._get_timestamp_et()}] Now monitoring 5-minute candles for breakouts...\n")
                    return  # Exit WITHOUT processing the 9:45 bar
                
                # Now process the bar (only bars before 9:45 AM)
                bar_high = float(bar.high)
                bar_low = float(bar.low)
                
                if self.orb_high is None:
                    self.orb_high = bar_high
                    self.orb_low = bar_low
                    print(f"[{self._get_timestamp_et()}] ORB tracking started - First bar: High=${bar_high:.2f}, Low=${bar_low:.2f}")
                else:
                    self.orb_high = max(self.orb_high, bar_high)
                    self.orb_low = min(self.orb_low, bar_low)
                
                return
            
            # Phase 2: After ORB, aggregate into 5-min candles
            if self.orb_established and not self.position_entered and self.trades_today < MAX_TRADES_PER_DAY:
                await self.aggregate_5min_candle(bar)
            
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR in handle_nvda_bar: {e}")
    
    def calculate_position_size(self, entry_price):
        """
        Calculate shares for a fixed $20K ETF position size.

        Since we trade the ETF directly, the ETF price already reflects its
        leverage. Expected loss is therefore based on the ETF stop distance
        without applying another 2x multiplier in the log output.
        """
        shares = int(ACCOUNT_SIZE / entry_price)
        notional_value = shares * entry_price
        max_loss = shares * entry_price * (HARD_STOP_PCT / 100)
        max_loss_pct = (max_loss / ACCOUNT_SIZE) * 100

        return shares, notional_value, max_loss, max_loss_pct

    def get_exit_label(self, order_type_value=None):
        """Describe whether the exit came from a hard stop or trailing stop."""
        if order_type_value and "trailing" in order_type_value:
            return "TRAILING STOP HIT"
        if self.profit_target_hit:
            return "TRAILING STOP HIT"
        return "STOP LOSS HIT"

    def log_exit_fill_details(self, symbol: str):
        """
        Log the actual Alpaca exit fill price and realized P&L when a stop
        order closes the position.
        """
        if not self.stop_loss_order_id:
            return False

        try:
            exit_order = self.trading_client.get_order_by_id(self.stop_loss_order_id)
            filled_avg_price = getattr(exit_order, 'filled_avg_price', None)
            filled_qty = getattr(exit_order, 'filled_qty', None)
            order_type = getattr(exit_order, 'order_type', None)
            order_type_value = order_type.value if hasattr(order_type, 'value') else str(order_type)

            if filled_avg_price is None or filled_qty is None or float(filled_qty) == 0:
                return False

            exit_price = float(filled_avg_price)
            exit_qty = float(filled_qty)
            exit_label = self.get_exit_label(order_type_value)

            log_and_flush(f"\n{'='*70}")
            log_and_flush(f"{exit_label} - FILLED WITH ALPACA")
            log_and_flush(f"{'='*70}")
            log_and_flush(f"Symbol: {symbol}")
            log_and_flush(f"Order ID: {exit_order.id}")
            log_and_flush(f"Order Type: {order_type_value}")
            log_and_flush(f"Shares Filled: {int(exit_qty)}")
            log_and_flush(f"Exit Price: ${exit_price:.6f}")

            if self.entry_price is not None:
                price_change = exit_price - self.entry_price
                realized_pl = price_change * exit_qty
                realized_pl_pct = (price_change / self.entry_price) * 100
                log_and_flush(f"Entry Price: ${self.entry_price:.2f}")
                log_and_flush(f"Realized P&L: ${realized_pl:.2f} ({realized_pl_pct:+.2f}%)")

            log_and_flush(f"CLOSURE VERIFIED WITH ALPACA")
            log_and_flush(f"   {symbol} position no longer exists in account")
            log_and_flush(f"{'='*70}\n")
            return True
        except Exception as e:
            log_and_flush(f"[{self._get_timestamp_et()}] WARNING: Could not fetch Alpaca exit fill details: {e}")
            return False

    def _order_status_value(self, order):
        """Normalize Alpaca order status values to lowercase strings."""
        status = getattr(order, 'status', None)
        if hasattr(status, 'value'):
            return status.value.lower()
        return str(status).lower()

    def _order_type_value(self, order):
        """Normalize Alpaca order type values to lowercase strings."""
        order_type = getattr(order, 'order_type', getattr(order, 'type', None))
        if hasattr(order_type, 'value'):
            return order_type.value.lower()
        return str(order_type).lower()

    def get_protective_exit_side(self):
        """Return the exit side for the currently open ETF position."""
        return OrderSide.SELL if self.position_side == 'long' else OrderSide.BUY

    def get_hard_stop_price(self):
        """Calculate the current hard-stop price from the entry fill."""
        if self.entry_price is None:
            return None
        if self.position_side == 'long':
            return round(self.entry_price * (1 - HARD_STOP_PCT / 100), 2)
        return round(self.entry_price * (1 + HARD_STOP_PCT / 100), 2)

    def get_active_exit_orders(self, symbol):
        """Return open stop and trailing-stop orders for a symbol."""
        exit_orders = []
        for order in self.trading_client.get_orders():
            if getattr(order, 'symbol', None) != symbol:
                continue
            if self._order_type_value(order) in {'stop', 'trailing_stop'}:
                exit_orders.append(order)
        return exit_orders

    def reset_position_state(self):
        """Clear in-memory state once Alpaca confirms the position is flat."""
        self.position_entered = False
        self.position_side = None
        self.entry_price = None
        self.entry_ticker = None
        self.active_ticker = None
        self.shares = 0
        self.stop_loss_order_id = None
        self.profit_target_hit = False
        self.trailing_upgrade_in_progress = False
        self.trailing_upgrade_retry_after = None
        self.highest_price_since_entry = None
        self.lowest_price_since_entry = None

    async def wait_for_order_status(self, order_id, target_statuses, label, failure_statuses=None, timeout_seconds=ORDER_STATE_TIMEOUT_SECONDS, missing_is_success=False):
        """Poll Alpaca until an order reaches the expected state."""
        target_statuses = {status.lower() for status in target_statuses}
        failure_statuses = {status.lower() for status in (failure_statuses or set())}
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        last_status = "unknown"
        last_order = None

        while asyncio.get_running_loop().time() < deadline:
            try:
                last_order = self.trading_client.get_order_by_id(order_id)
            except Exception as e:
                if missing_is_success:
                    log_and_flush(f"{label} no longer retrievable in Alpaca - treating as complete")
                    return True, None
                last_status = f"lookup_error: {e}"
                await asyncio.sleep(ORDER_STATE_POLL_SECONDS)
                continue

            last_status = self._order_status_value(last_order)
            if last_status in target_statuses:
                return True, last_order
            if last_status in failure_statuses:
                return False, last_order

            await asyncio.sleep(ORDER_STATE_POLL_SECONDS)

        log_and_flush(f"WARNING: Timed out waiting for {label} (last status: {last_status})")
        return False, last_order

    async def cancel_order_and_wait(self, order_id, label):
        """Cancel an order and wait for Alpaca to release the reserved shares."""
        try:
            self.trading_client.cancel_order_by_id(order_id)
            log_and_flush(f"{label} cancel submitted - waiting for Alpaca confirmation")
        except Exception as e:
            log_and_flush(f"ERROR canceling {label}: {e}")
            return False

        success, order = await self.wait_for_order_status(
            order_id=order_id,
            target_statuses={'canceled', 'cancelled'},
            failure_statuses={'filled', 'rejected', 'expired'},
            label=label,
            missing_is_success=True
        )
        if success:
            log_and_flush(f"{label} canceled - shares are free again")
            return True

        status = self._order_status_value(order) if order else 'unknown'
        log_and_flush(f"ERROR: {label} did not cancel cleanly (status: {status})")
        return False

    async def submit_plain_stop_order(self, symbol, qty, stop_price, exit_side, label):
        """Submit a standalone stop order and wait for Alpaca to accept it."""
        try:
            stop_request = StopOrderRequest(
                symbol=symbol,
                qty=qty,
                side=exit_side,
                time_in_force=TimeInForce.DAY,
                stop_price=stop_price
            )
            stop_order = self.trading_client.submit_order(stop_request)
            log_and_flush(f"{label} submitted - Order ID: {stop_order.id} @ ${stop_price:.2f}")
        except Exception as e:
            log_and_flush(f"CRITICAL: Failed to submit {label.lower()}: {e}")
            return None

        success, confirmed_order = await self.wait_for_order_status(
            order_id=stop_order.id,
            target_statuses={'new', 'accepted', 'pending_new', 'accepted_for_bidding', 'partially_filled'},
            failure_statuses={'rejected', 'canceled', 'cancelled', 'expired'},
            label=label
        )
        if not success:
            return None

        return confirmed_order.id if confirmed_order else stop_order.id

    async def submit_replacement_hard_stop(self):
        """Re-arm a plain hard stop if the trailing-stop upgrade fails."""
        stop_price = self.get_hard_stop_price()
        if stop_price is None:
            log_and_flush("ERROR: Cannot restore hard stop without an entry price")
            return False

        stop_order_id = await self.submit_plain_stop_order(
            symbol=self.entry_ticker,
            qty=self.shares,
            stop_price=stop_price,
            exit_side=self.get_protective_exit_side(),
            label="Replacement hard stop"
        )
        if not stop_order_id:
            return False

        self.stop_loss_order_id = stop_order_id
        log_and_flush("Hard stop protection restored")
        return True

    def activate_live_position(self, ticker, side, fill_price, filled_qty):
        """Record the actual Alpaca fill as the bot's live position."""
        self.position_entered = True
        self.position_side = 'long' if side == OrderSide.BUY else 'short'
        self.entry_ticker = ticker
        self.entry_price = fill_price
        self.shares = filled_qty
        self.stop_loss_order_id = None
        self.profit_target_hit = False
        self.trailing_upgrade_in_progress = False
        self.trailing_upgrade_retry_after = None
        self.highest_price_since_entry = fill_price
        self.lowest_price_since_entry = fill_price
        self.trades_today = MAX_TRADES_PER_DAY

    async def cancel_active_exit_orders(self, symbol, context):
        """Cancel any stop or trailing orders still active for the symbol."""
        try:
            exit_orders = self.get_active_exit_orders(symbol)
        except Exception as e:
            log_and_flush(f"WARNING: Could not inspect active exit orders after {context}: {e}")
            return False

        if not exit_orders:
            return True

        all_canceled = True
        for exit_order in exit_orders:
            label = f"{context} cleanup order {exit_order.id}"
            if not await self.cancel_order_and_wait(exit_order.id, label):
                all_canceled = False
        return all_canceled

    async def wait_for_position_closed(self, symbol, timeout_seconds=ORDER_STATE_TIMEOUT_SECONDS):
        """Poll Alpaca until the position is no longer open."""
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        last_qty = None

        while asyncio.get_running_loop().time() < deadline:
            try:
                position = self.trading_client.get_open_position(symbol)
                last_qty = float(position.qty)
                await asyncio.sleep(ORDER_STATE_POLL_SECONDS)
            except Exception as e:
                if is_missing_position_error(e):
                    return True, None
                log_and_flush(f"WARNING checking whether {symbol} is closed: {e}")
                await asyncio.sleep(ORDER_STATE_POLL_SECONDS)

        return False, last_qty
    
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
    
    def check_for_unexpected_positions(self):
        """
        Check for unexpected positions that shouldn't exist.
        Returns True if unexpected positions found, False otherwise.
        Bot should STOP if this returns True - requires manual investigation.
        """
        try:
            positions = self.trading_client.get_all_positions()
            unexpected_found = False
            
            for position in positions:
                if position.symbol in [LONG_TICKER, SHORT_TICKER]:
                    qty = float(position.qty)
                    current_price = float(position.current_price)
                    unrealized_pl = float(position.unrealized_pl)
                    unrealized_pl_pct = float(position.unrealized_plpc) * 100
                    market_value = float(position.market_value)
                    
                    log_and_flush(f"\n{'='*70}")
                    log_and_flush(f"UNEXPECTED POSITION DETECTED - BOT STOPPING")
                    log_and_flush(f"{'='*70}")
                    log_and_flush(f"Symbol: {position.symbol}")
                    log_and_flush(f"Shares: {int(qty)}")
                    log_and_flush(f"Current Price: ${current_price:.2f}")
                    log_and_flush(f"Market Value: ${market_value:.2f}")
                    log_and_flush(f"Unrealized P&L: ${unrealized_pl:.2f} ({unrealized_pl_pct:+.2f}%)")
                    log_and_flush(f"")
                    log_and_flush(f"POSSIBLE CAUSES:")
                    log_and_flush(f"  1. Position from previous day didn't close (check yesterday's logs)")
                    log_and_flush(f"  2. Manual trade entered in Alpaca dashboard")
                    log_and_flush(f"  3. Bot crashed before closing position")
                    log_and_flush(f"  4. Another bot/strategy using same account")
                    log_and_flush(f"")
                    log_and_flush(f"REQUIRED ACTIONS:")
                    log_and_flush(f"  1. Go to Alpaca dashboard: https://app.alpaca.markets/paper/dashboard/overview")
                    log_and_flush(f"  2. Review the position and decide:")
                    log_and_flush(f"     - If it's an error: Close manually in Alpaca dashboard")
                    log_and_flush(f"     - If it's intentional: Let it run (bot will not enter new trades today)")
                    log_and_flush(f"  3. Check yesterday's logs to understand what happened")
                    log_and_flush(f"  4. Once resolved, the bot will retry automatically")
                    log_and_flush(f"")
                    log_and_flush(f"BOT WILL EXIT IN 60 SECONDS TO ALLOW MANUAL REVIEW")
                    log_and_flush(f"{'='*70}\n")
                    
                    unexpected_found = True
            
            return unexpected_found
            
        except Exception as e:
            log_and_flush(f"[{self._get_timestamp_et()}] ERROR checking for unexpected positions: {e}")
            return False
    
    async def get_latest_price(self, ticker: str):
        """Get the latest quote price for a ticker"""
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            latest_quote = self.data_client.get_stock_latest_quote(request)
            
            if ticker in latest_quote:
                ask_price = float(latest_quote[ticker].ask_price)
                bid_price = float(latest_quote[ticker].bid_price)

                if bid_price > 0 and ask_price > 0:
                    reference_price = (ask_price + bid_price) / 2
                elif ask_price > 0:
                    reference_price = ask_price
                elif bid_price > 0:
                    reference_price = bid_price
                else:
                    print(f"[{self._get_timestamp_et()}] ERROR: Invalid quote for {ticker} (bid/ask are zero)")
                    return None

                print(
                    f"[{self._get_timestamp_et()}] {ticker} Latest Quote - "
                    f"Bid: ${bid_price:.2f}, Ask: ${ask_price:.2f}, Ref: ${reference_price:.2f}"
                )
                return reference_price
            else:
                print(f"[{self._get_timestamp_et()}] ERROR: No quote data for {ticker}")
                return None
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR getting latest price for {ticker}: {e}")
            return None
    
    async def place_trade_with_stop(self, ticker: str, side: OrderSide, nvda_signal_price: float):
        """Place trade with bracket order (entry + stop loss)"""
        try:
            # Get the actual current price of the ETF we're trading
            etf_price = await self.get_latest_price(ticker)
            if etf_price is None:
                print(f"[{self._get_timestamp_et()}] ERROR: Could not get price for {ticker}. Order cancelled.")
                return False
            
            # Calculate position size based on ETF price (not NVDA price!)
            shares, notional_value, max_loss, max_loss_pct = self.calculate_position_size(etf_price)
            
            if shares <= 0:
                print(f"[{self._get_timestamp_et()}] ERROR: Invalid position size ({shares} shares)")
                return False
            
            # Calculate stop loss price based on ETF price
            # IMPORTANT: Must round to 2 decimals - Alpaca requires penny increments for stocks > $1
            if side == OrderSide.BUY:
                stop_price = round(etf_price * (1 - HARD_STOP_PCT / 100), 2)
            else:
                stop_price = round(etf_price * (1 + HARD_STOP_PCT / 100), 2)

            log_and_flush(f"\n[{self._get_timestamp_et()}] {'LONG' if side == OrderSide.BUY else 'SHORT'} SIGNAL DETECTED")
            log_and_flush(f"[{self._get_timestamp_et()}] NVDA Signal Price: ${nvda_signal_price:.2f}")
            log_and_flush(f"[{self._get_timestamp_et()}] TRADE SETUP:")
            log_and_flush(f"[{self._get_timestamp_et()}]   Ticker: {ticker}")
            log_and_flush(f"[{self._get_timestamp_et()}]   Reference ETF Price: ${etf_price:.2f}")
            log_and_flush(f"[{self._get_timestamp_et()}]   Shares: {shares}")
            log_and_flush(f"[{self._get_timestamp_et()}]   Position Value: ${notional_value:.2f}")
            log_and_flush(f"[{self._get_timestamp_et()}]   Expected Max Loss: ${max_loss:.2f} ({max_loss_pct:.2f}% of account)")
            log_and_flush(f"[{self._get_timestamp_et()}]   Stop Loss: ${stop_price:.2f} (-{HARD_STOP_PCT}%)")
            log_and_flush(f"[{self._get_timestamp_et()}] PLACING {'LONG' if side == OrderSide.BUY else 'SHORT'} ORDER")
            
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
            log_and_flush(f"[{self._get_timestamp_et()}] Order submitted - Order ID: {order.id}")
            
            # Wait for order to fill and verify
            await asyncio.sleep(3)
            
            # Check order status
            filled_order = self.trading_client.get_order_by_id(order.id)
            order_status = self._order_status_value(filled_order)
            filled_qty = float(getattr(filled_order, 'filled_qty', 0) or 0)
            filled_avg_price = getattr(filled_order, 'filled_avg_price', None)
            actual_fill_price = float(filled_avg_price) if filled_avg_price is not None and filled_qty > 0 else None

            if order_status == 'filled':
                
                log_and_flush(f"\n{'='*70}")
                log_and_flush(f"TRADE OPENED - CONFIRMED WITH ALPACA")
                log_and_flush(f"{'='*70}")
                log_and_flush(f"Order ID: {order.id}")
                log_and_flush(f"Symbol: {ticker}")
                log_and_flush(f"Side: {'LONG' if side == OrderSide.BUY else 'SHORT'}")
                log_and_flush(f"Shares Filled: {int(filled_qty)}")
                log_and_flush(f"Fill Price: ${actual_fill_price:.2f}")
                log_and_flush(f"Position Value: ${actual_fill_price * filled_qty:.2f}")
                log_and_flush(f"Stop Loss: ${stop_price:.2f} (-{HARD_STOP_PCT}%)")
                log_and_flush(f"Expected Max Loss: ${max_loss:.2f} ({max_loss_pct:.2f}% of account)")
                log_and_flush(f"Status: {filled_order.status.upper()}")
                log_and_flush(f"Timestamp: {self._get_timestamp_et()}")
                log_and_flush(f"{'='*70}\n")
                
                # Verify position exists in Alpaca
                try:
                    position = self.trading_client.get_open_position(ticker)
                    log_and_flush(f"POSITION VERIFIED IN ALPACA:")
                    log_and_flush(f"   Symbol: {position.symbol}")
                    log_and_flush(f"   Qty: {float(position.qty)}")
                    log_and_flush(f"   Current Price: ${float(position.current_price):.2f}")
                    log_and_flush(f"   Market Value: ${float(position.market_value):.2f}\n")
                except Exception as e:
                    log_and_flush(f"WARNING: Could not verify position in Alpaca: {e}\n")
                
                # NOW set position state (only after confirming fill)
                self.activate_live_position(ticker, side, actual_fill_price, filled_qty)
                
                # Log exit strategy clearly
                log_and_flush(f"===== EXIT STRATEGY ACTIVE =====")
                log_and_flush(f"1. HARD STOP @ ${stop_price:.2f} (-{HARD_STOP_PCT}%) - Set on Alpaca, executes automatically")
                log_and_flush(f"2. PROFIT TARGET @ ${actual_fill_price * (1 + PROFIT_TARGET_PCT / 100):.2f} (+{PROFIT_TARGET_PCT}%) - Upgrades to {TRAILING_STOP_PCT}% trailing stop")
                log_and_flush(f"3. END OF DAY EXIT @ 2:30 PM CST (3:30 PM ET) - Forced exit regardless of P&L")
                log_and_flush(f"Monitoring position for stop hits and profit target...")
                log_and_flush(f"=================================\n")
                
                # Initialize price tracking for trailing stop
                # Get stop loss order ID
                await self.get_child_orders(order.id)
                
                return True
            elif order_status == 'partially_filled' and filled_qty > 0 and actual_fill_price is not None:
                log_and_flush(f"\n{'='*70}")
                log_and_flush(f"PARTIAL FILL DETECTED - PROTECTING LIVE POSITION")
                log_and_flush(f"{'='*70}")
                log_and_flush(f"Order ID: {order.id}")
                log_and_flush(f"Symbol: {ticker}")
                log_and_flush(f"Requested Shares: {shares}")
                log_and_flush(f"Shares Filled: {int(filled_qty)}")
                log_and_flush(f"Unfilled Shares: {int(shares - filled_qty)}")
                log_and_flush(f"Fill Price: ${actual_fill_price:.2f}")
                log_and_flush(f"Status After 3s Check: {order_status.upper()}")

                cancel_ok = await self.cancel_order_and_wait(order.id, "Unfilled entry remainder")
                if not cancel_ok:
                    log_and_flush("WARNING: Could not confirm the unfilled remainder was canceled cleanly")

                cleanup_ok = await self.cancel_active_exit_orders(ticker, "Partial-fill entry")
                if not cleanup_ok:
                    log_and_flush("WARNING: Could not fully clear old exit orders before installing a new stop")

                self.activate_live_position(ticker, side, actual_fill_price, filled_qty)
                replacement_stop_id = await self.submit_replacement_hard_stop()
                if not replacement_stop_id:
                    log_and_flush("CRITICAL: Partial fill exists but hard-stop protection could not be restored")
                    log_and_flush("Attempting emergency close of the partial position...")
                    await self.close_all_positions(f"UNPROTECTED PARTIAL FILL for {ticker}")
                    return False

                log_and_flush(f"Replacement Stop Loss: ${stop_price:.2f} (-{HARD_STOP_PCT}%)")
                log_and_flush(f"Expected Max Loss On Filled Shares: ${actual_fill_price * filled_qty * (HARD_STOP_PCT / 100):.2f}")
                log_and_flush(f"Status: PARTIALLY FILLED POSITION IS NOW PROTECTED")
                log_and_flush(f"Timestamp: {self._get_timestamp_et()}")
                log_and_flush(f"{'='*70}\n")

                log_and_flush(f"===== EXIT STRATEGY ACTIVE =====")
                log_and_flush(f"1. HARD STOP @ ${stop_price:.2f} (-{HARD_STOP_PCT}%) - Replaced after partial fill")
                log_and_flush(f"2. PROFIT TARGET @ ${actual_fill_price * (1 + PROFIT_TARGET_PCT / 100):.2f} (+{PROFIT_TARGET_PCT}%) - Upgrades to {TRAILING_STOP_PCT}% trailing stop")
                log_and_flush(f"3. END OF DAY EXIT @ 2:30 PM CST (3:30 PM ET) - Forced exit regardless of P&L")
                log_and_flush(f"Monitoring position for stop hits and profit target...")
                log_and_flush(f"=================================\n")
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

                # A timeout can still leave a small fill behind; flatten it if that happened.
                try:
                    position = self.trading_client.get_open_position(ticker)
                    actual_qty = float(position.qty)
                    if actual_qty > 0:
                        log_and_flush(f"[{self._get_timestamp_et()}] WARNING: Entry order timed out but Alpaca shows {actual_qty} shares open")
                        self.activate_live_position(
                            ticker,
                            side,
                            float(getattr(position, 'avg_entry_price', etf_price)),
                            actual_qty
                        )
                        await self.cancel_active_exit_orders(ticker, "Timed-out entry")
                        await self.close_all_positions(f"ENTRY TIMED OUT AFTER 3 SECONDS - FLATTENING {ticker}")
                except Exception as position_error:
                    if not is_missing_position_error(position_error):
                        log_and_flush(f"[{self._get_timestamp_et()}] WARNING checking for leftover shares after timeout: {position_error}")
                
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
            # Fallback: if nested legs are unavailable, discover active protective exits directly.
            if not self.stop_loss_order_id and self.entry_ticker:
                exit_orders = self.get_active_exit_orders(self.entry_ticker)
                if exit_orders:
                    self.stop_loss_order_id = exit_orders[0].id
                    log_and_flush(
                        f"[{self._get_timestamp_et()}] Protective order discovered via open-order scan: "
                        f"{self.stop_loss_order_id} ({self._order_type_value(exit_orders[0])})"
                    )
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
        if self.profit_target_hit or not self.position_entered or self.trailing_upgrade_in_progress:
            return
        if self.trailing_upgrade_retry_after and datetime.now(TIMEZONE_ET) < self.trailing_upgrade_retry_after:
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
                log_and_flush(f"\n{'='*70}")
                log_and_flush(f"PROFIT TARGET HIT - UPGRADING TO TRAILING STOP")
                log_and_flush(f"{'='*70}")
                log_and_flush(f"Current P&L: ${unrealized_pl:.2f} (Target: ${ACCOUNT_SIZE * PROFIT_TARGET_PCT / 100:.2f})")
                log_and_flush(f"Current Price: ${current_price:.2f}")
                log_and_flush(f"Upgrading to {TRAILING_STOP_PCT}% Trailing Stop...")
                log_and_flush(f"")

                self.trailing_upgrade_in_progress = True
                try:
                    # Always clear any active protective exits first (even if stop_loss_order_id is missing).
                    active_exits = self.get_active_exit_orders(self.entry_ticker)
                    if active_exits:
                        if not self.stop_loss_order_id:
                            self.stop_loss_order_id = active_exits[0].id
                            log_and_flush(
                                f"Detected existing protective order despite missing cached ID: {self.stop_loss_order_id} "
                                f"({self._order_type_value(active_exits[0])})"
                            )
                        log_and_flush(f"Step 1/4: Cancel {len(active_exits)} existing protective order(s)")
                        canceled = await self.cancel_active_exit_orders(self.entry_ticker, "Trailing-stop upgrade")
                        if not canceled:
                            self.trailing_upgrade_retry_after = datetime.now(TIMEZONE_ET) + timedelta(seconds=TRAILING_UPGRADE_RETRY_DELAY_SECONDS)
                            log_and_flush("Trailing-stop upgrade aborted - protective order cancel still pending")
                            log_and_flush(f"Will retry trailing-stop upgrade after {self.trailing_upgrade_retry_after.strftime('%H:%M:%S ET')}")
                            log_and_flush(f"{'='*70}\n")
                            return
                        self.stop_loss_order_id = None
                    else:
                        log_and_flush("Step 1/4: No active protective orders found to cancel")

                    log_and_flush("Step 2/4: Submit trailing stop")
                    trailing_stop_request = TrailingStopOrderRequest(
                        symbol=self.entry_ticker,
                        qty=self.shares,
                        side=self.get_protective_exit_side(),
                        time_in_force=TimeInForce.DAY,
                        trail_percent=TRAILING_STOP_PCT
                    )
                    
                    trailing_order = self.trading_client.submit_order(trailing_stop_request)
                    log_and_flush(f"Trailing stop submitted - Order ID: {trailing_order.id}")
                    log_and_flush("Step 3/4: Wait for Alpaca to confirm the trailing stop is active")

                    success, confirmed_order = await self.wait_for_order_status(
                        order_id=trailing_order.id,
                        target_statuses={'new', 'accepted', 'pending_new', 'accepted_for_bidding', 'partially_filled'},
                        failure_statuses={'rejected', 'canceled', 'cancelled', 'expired'},
                        label="Trailing stop"
                    )
                    if not success:
                        raise RuntimeError("Trailing stop was not accepted by Alpaca")

                    self.stop_loss_order_id = confirmed_order.id if confirmed_order else trailing_order.id
                    self.profit_target_hit = True
                    self.trailing_upgrade_retry_after = None
                    log_and_flush("Step 4/4: Upgrade confirmed")
                    log_and_flush("")
                    log_and_flush("UPGRADE COMPLETE")
                    log_and_flush(f"   Protection: {TRAILING_STOP_PCT}% Trailing Stop now active")
                    log_and_flush("   Stop will move up as price increases")
                    log_and_flush(f"{'='*70}\n")
                except Exception as e:
                    error_text = str(e).lower()
                    log_and_flush(f"ERROR upgrading to trailing stop: {e}")
                    self.trailing_upgrade_retry_after = datetime.now(TIMEZONE_ET) + timedelta(seconds=TRAILING_UPGRADE_RETRY_DELAY_SECONDS)

                    # Alpaca can report qty=0 while another protective order still reserves shares.
                    if "insufficient qty available for order" in error_text:
                        log_and_flush("Detected reserved shares from an existing protective order. Keeping current protection and retrying upgrade.")
                        existing_exits = self.get_active_exit_orders(self.entry_ticker)
                        if existing_exits:
                            self.stop_loss_order_id = existing_exits[0].id
                            log_and_flush(
                                f"Existing protection still active: {self.stop_loss_order_id} "
                                f"({self._order_type_value(existing_exits[0])})"
                            )
                        else:
                            log_and_flush("No active protective order found after rejection - attempting to restore hard stop...")
                            restored = await self.submit_replacement_hard_stop()
                            if restored:
                                log_and_flush(f"Hard stop restored. Next upgrade retry after {self.trailing_upgrade_retry_after.strftime('%H:%M:%S ET')}")
                            else:
                                log_and_flush("CRITICAL: Hard stop could not be restored automatically. Check Alpaca immediately.")
                    else:
                        log_and_flush("Attempting to restore hard-stop protection...")
                        restored = await self.submit_replacement_hard_stop()
                        if restored:
                            log_and_flush(f"Hard stop restored. Next upgrade retry after {self.trailing_upgrade_retry_after.strftime('%H:%M:%S ET')}")
                        else:
                            log_and_flush("CRITICAL: Hard stop could not be restored automatically. Check Alpaca immediately.")
                    log_and_flush(f"{'='*70}\n")
                    return
                finally:
                    self.trailing_upgrade_in_progress = False
        
        except Exception as e:
            print(f"[{self._get_timestamp_et()}] ERROR checking profit target: {e}")
    
    async def close_all_positions(self, reason=""):
        """Close all positions and verify with Alpaca"""
        try:
            log_and_flush(f"\n{'='*70}")
            log_and_flush(f"CLOSING ALL POSITIONS - {reason}")
            log_and_flush(f"{'='*70}")
            
            positions = self.trading_client.get_all_positions()
            
            for position in positions:
                if position.symbol in [LONG_TICKER, SHORT_TICKER]:
                    # Log position details before closing
                    final_pl = float(position.unrealized_pl)
                    final_pl_pct = float(position.unrealized_plpc) * 100
                    current_price = float(position.current_price)
                    qty = float(position.qty)
                    market_value = float(position.market_value)
                    
                    log_and_flush(f"Symbol: {position.symbol}")
                    log_and_flush(f"Side: {self.position_side if self.position_side else 'UNKNOWN'}")
                    
                    # Only show entry price if we have it
                    if self.entry_price is not None:
                        log_and_flush(f"Entry Price: ${self.entry_price:.2f}")
                        log_and_flush(f"Exit Price: ${current_price:.2f}")
                        price_change = current_price - self.entry_price if self.position_side == 'long' else self.entry_price - current_price
                        log_and_flush(f"Price Change: ${price_change:.2f} ({(price_change/self.entry_price)*100:+.2f}%)")
                    else:
                        log_and_flush(f"Exit Price: ${current_price:.2f} (Entry unknown - bot restarted)")
                    
                    log_and_flush(f"Shares: {int(qty)}")
                    log_and_flush(f"Market Value: ${market_value:.2f}")
                    log_and_flush(f"Final P&L: ${final_pl:.2f} ({final_pl_pct:+.2f}%)")
                    log_and_flush(f"")
                    
                    # STEP 1: Cancel active stop orders BEFORE closing
                    stop_orders_found = []
                    try:
                        for order in self.get_active_exit_orders(position.symbol):
                            stop_orders_found.append({
                                'id': order.id,
                                'type': self._order_type_value(order),
                                'stop_price': getattr(order, 'stop_price', None),
                                'trail_percent': getattr(order, 'trail_percent', None)
                            })
                        
                        if stop_orders_found:
                            log_and_flush(f"Active stop order(s) found:")
                            for stop in stop_orders_found:
                                log_and_flush(f"   - Type: {stop['type']}, ID: {stop['id']}")
                    except Exception as e:
                        log_and_flush(f"Could not check for stop orders: {e}")
                    
                    if stop_orders_found:
                        log_and_flush(f"")
                        log_and_flush(f"Canceling protective orders before market close...")
                        all_canceled = True
                        for stop in stop_orders_found:
                            label = f"{stop['type']} order {stop['id']}"
                            if not await self.cancel_order_and_wait(stop['id'], label):
                                all_canceled = False
                        
                        if not all_canceled:
                            log_and_flush(f"ERROR: Could not clear all protective orders. Skipping close attempt to avoid an insufficient-qty rejection.")
                            log_and_flush(f"Check Alpaca dashboard immediately!")
                            continue
                        
                        remaining_exit_orders = self.get_active_exit_orders(position.symbol)
                        if remaining_exit_orders:
                            log_and_flush(f"ERROR: Alpaca still shows active protective orders after cancel attempts.")
                            for order in remaining_exit_orders:
                                log_and_flush(f"   Remaining order: {order.id} ({self._order_type_value(order)})")
                            log_and_flush(f"Skipping close attempt until shares are fully released.")
                            continue
                    
                    # STEP 2: Close the position after exits are cleared
                    log_and_flush(f"")
                    log_and_flush(f"Protective orders cleared - submitting market close")
                    close_order = self.trading_client.close_position(position.symbol)
                    close_order_id = getattr(close_order, 'id', None)
                    if close_order_id:
                        log_and_flush(f"Close order submitted to Alpaca - Order ID: {close_order_id}")
                    else:
                        log_and_flush(f"Close order submitted to Alpaca")
                    
                    # STEP 3: Wait for close to process
                    position_closed, remaining_qty = await self.wait_for_position_closed(position.symbol, timeout_seconds=12)
                    
                    # STEP 4: Verify position is closed
                    if position_closed:
                        log_and_flush(f"")
                        log_and_flush(f"POSITION CLOSED - VERIFIED WITH ALPACA")
                        log_and_flush(f"   {position.symbol} position no longer exists in account")
                    else:
                        log_and_flush(f"")
                        log_and_flush(f"WARNING: Position still exists after close attempt!")
                        if remaining_qty is not None:
                            log_and_flush(f"   Current qty: {remaining_qty}")
                        log_and_flush(f"   Check Alpaca dashboard immediately!")
            
            open_strategy_positions = []
            try:
                for position in self.trading_client.get_all_positions():
                    if position.symbol in [LONG_TICKER, SHORT_TICKER]:
                        open_strategy_positions.append(position.symbol)
            except Exception as e:
                log_and_flush(f"WARNING: Could not run final position verification: {e}")

            if not open_strategy_positions:
                try:
                    remaining_orders = self.trading_client.get_orders()
                    if remaining_orders:
                        log_and_flush(f"")
                        log_and_flush(f"Found {len(remaining_orders)} remaining order(s) after flattening - canceling...")
                        self.trading_client.cancel_orders()
                        log_and_flush(f"All remaining orders canceled")
                    else:
                        log_and_flush(f"")
                        log_and_flush(f"No pending orders remaining")
                except Exception as e:
                    log_and_flush(f"WARNING: Error checking pending orders: {e}")

                log_and_flush(f"{'='*70}\n")
                self.reset_position_state()
            else:
                log_and_flush(f"{'='*70}\n")
                log_and_flush(f"WARNING: Strategy position still open after close sequence: {', '.join(open_strategy_positions)}")
                log_and_flush(f"Keeping in-memory position state intact for the next retry or manual intervention.")
            
        except Exception as e:
            log_and_flush(f"ERROR closing positions: {e}")
            log_and_flush(f"Check Alpaca dashboard immediately: https://app.alpaca.markets/paper/dashboard/overview")
    
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
            
            # Safety check: Ensure ORB was established before checking breakouts
            if self.orb_high is None or self.orb_low is None:
                print(f"[{self._get_timestamp_et()}] WARNING: ORB not established - cannot check breakouts")
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
                    if not self.log_exit_fill_details(LONG_TICKER):
                        expected_stop = round(self.entry_price * (1 - HARD_STOP_PCT / 100), 2)
                        estimated_loss = (expected_stop - self.entry_price) * self.shares

                        log_and_flush(f"\n{'='*70}")
                        log_and_flush(f"STOP LOSS HIT - POSITION CLOSED BY ALPACA")
                        log_and_flush(f"{'='*70}")
                        log_and_flush(f"Symbol: {LONG_TICKER}")
                        log_and_flush(f"Entry Price: ${self.entry_price:.2f}")
                        log_and_flush(f"Expected Stop: ${expected_stop:.2f}")
                        log_and_flush(f"Estimated Loss: ${estimated_loss:.2f} (-{HARD_STOP_PCT}%)")
                        log_and_flush(f"")
                        log_and_flush(f"POSITION CLOSED - VERIFIED WITH ALPACA")
                        log_and_flush(f"   {LONG_TICKER} position no longer exists in account")
                        log_and_flush(f"   Check Alpaca dashboard for exact fill price")
                        log_and_flush(f"   Dashboard: https://app.alpaca.markets/paper/dashboard/overview")
                        log_and_flush(f"{'='*70}\n")
                    
                    self.reset_position_state()
                    return
            except Exception as e:
                if not is_missing_position_error(e):
                    log_and_flush(f"[{self._get_timestamp_et()}] WARNING checking {LONG_TICKER} position: {e}")
                    log_and_flush(f"[{self._get_timestamp_et()}] Keeping position state intact and retrying on next trade update")
                    return

                if not self.log_exit_fill_details(LONG_TICKER):
                    log_and_flush(f"\n{'='*70}")
                    log_and_flush(f"POSITION CLOSED - STOP LOSS TRIGGERED")
                    log_and_flush(f"{'='*70}")
                    log_and_flush(f"Symbol: {LONG_TICKER}")
                    log_and_flush(f"Position no longer exists in Alpaca account")
                    log_and_flush(f"")
                    log_and_flush(f"CLOSURE VERIFIED WITH ALPACA")
                    log_and_flush(f"   Likely stop loss order executed")
                    log_and_flush(f"   Check dashboard for exact exit details:")
                    log_and_flush(f"   https://app.alpaca.markets/paper/dashboard/overview")
                    log_and_flush(f"{'='*70}\n")

                self.reset_position_state()
                return
            
            # Check for end of day exit
            if current_time_cst >= END_OF_DAY_EXIT:
                await self.close_all_positions(f"END OF DAY EXIT at {self._get_timestamp_cst()}")
                print(f"[{self._get_timestamp_cst()}] End of trading day reached. Bot stopping.")
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
                    if not self.log_exit_fill_details(SHORT_TICKER):
                        expected_stop = round(self.entry_price * (1 - HARD_STOP_PCT / 100), 2)
                        estimated_loss = (expected_stop - self.entry_price) * self.shares

                        log_and_flush(f"\n{'='*70}")
                        log_and_flush(f"STOP LOSS HIT - POSITION CLOSED BY ALPACA")
                        log_and_flush(f"{'='*70}")
                        log_and_flush(f"Symbol: {SHORT_TICKER}")
                        log_and_flush(f"Entry Price: ${self.entry_price:.2f}")
                        log_and_flush(f"Expected Stop: ${expected_stop:.2f}")
                        log_and_flush(f"Estimated Loss: ${estimated_loss:.2f} (-{HARD_STOP_PCT}%)")
                        log_and_flush(f"")
                        log_and_flush(f"POSITION CLOSED - VERIFIED WITH ALPACA")
                        log_and_flush(f"   {SHORT_TICKER} position no longer exists in account")
                        log_and_flush(f"   Check Alpaca dashboard for exact fill price")
                        log_and_flush(f"   Dashboard: https://app.alpaca.markets/paper/dashboard/overview")
                        log_and_flush(f"{'='*70}\n")
                    
                    self.reset_position_state()
                    return
            except Exception as e:
                if not is_missing_position_error(e):
                    log_and_flush(f"[{self._get_timestamp_et()}] WARNING checking {SHORT_TICKER} position: {e}")
                    log_and_flush(f"[{self._get_timestamp_et()}] Keeping position state intact and retrying on next trade update")
                    return

                if not self.log_exit_fill_details(SHORT_TICKER):
                    log_and_flush(f"\n{'='*70}")
                    log_and_flush(f"POSITION CLOSED - STOP LOSS TRIGGERED")
                    log_and_flush(f"{'='*70}")
                    log_and_flush(f"Symbol: {SHORT_TICKER}")
                    log_and_flush(f"Position no longer exists in Alpaca account")
                    log_and_flush(f"")
                    log_and_flush(f"CLOSURE VERIFIED WITH ALPACA")
                    log_and_flush(f"   Likely stop loss order executed")
                    log_and_flush(f"   Check dashboard for exact exit details:")
                    log_and_flush(f"   https://app.alpaca.markets/paper/dashboard/overview")
                    log_and_flush(f"{'='*70}\n")

                self.reset_position_state()
                return
            
            # Check for end of day exit
            if current_time_cst >= END_OF_DAY_EXIT:
                await self.close_all_positions(f"END OF DAY EXIT at {self._get_timestamp_cst()}")
                print(f"[{self._get_timestamp_cst()}] End of trading day reached. Bot stopping.")
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
        
        # STEP 2: Wait for market to open
        if not await self.wait_for_market_open():
            return  # Exit if market not open
        
        # STEP 3: Acquire connection lock to prevent multiple instances
        if not await acquire_connection_lock():
            log_and_flush(f"[ERROR] Cannot acquire connection lock - another instance is running")
            log_and_flush(f"[ERROR] Exiting to prevent connection limit errors")
            await asyncio.sleep(30)
            return
        
        # STEP 4: Test Alpaca API connection BEFORE subscribing to websockets
        if not await test_alpaca_connection(self.trading_client):
            log_and_flush(f"[ERROR] Cannot connect to Alpaca API - exiting")
            release_connection_lock()
            await asyncio.sleep(30)
            return
        
        # STEP 5: Check for unexpected positions from previous days
        log_and_flush(f"\n[{self._get_timestamp_et()}] Checking for unexpected positions...")
        if self.check_for_unexpected_positions():
            log_and_flush(f"[{self._get_timestamp_et()}] UNEXPECTED POSITION FOUND - STOPPING BOT")
            log_and_flush(f"[{self._get_timestamp_et()}] Manual intervention required - see details above")
            release_connection_lock()
            await asyncio.sleep(60)  # Give time to read logs
            return
        
        log_and_flush(f"[{self._get_timestamp_et()}] No unexpected positions - ready to trade")
        
        # STEP 6: Check if we can trade today (verify ORB window not missed)
        log_and_flush(f"\n[{self._get_timestamp_et()}] Checking trading day status...")
        now_et = datetime.now(TIMEZONE_ET)
        current_time_et = now_et.time()
        
        # Check if we missed the ORB window
        if current_time_et > time(9, 45):
            log_and_flush(f"[{self._get_timestamp_et()}] WARNING: Started after ORB period (9:30-9:45 AM ET)")
            log_and_flush(f"[{self._get_timestamp_et()}] Cannot establish Opening Range - no new trades today")
            log_and_flush(f"[{self._get_timestamp_et()}] Will monitor existing positions only until 2:30 PM CST exit")
            self.trades_today = MAX_TRADES_PER_DAY  # Prevent trading
        else:
            log_and_flush(f"[{self._get_timestamp_et()}] Ready to trade - ORB period active or upcoming")
        
        print(f"\n[{self._get_timestamp_et()}] STRATEGY CONFIGURATION:")
        print(f"[{self._get_timestamp_et()}] Phase 1 (9:30-9:45 AM): Track 15-min ORB")
        print(f"[{self._get_timestamp_et()}] Phase 2 (After 9:45 AM): Monitor 5-min candles for breakouts")
        print(f"[{self._get_timestamp_et()}] Long Entry: 5-min body entirely above ORB High -> Buy {LONG_TICKER}")
        print(f"[{self._get_timestamp_et()}] Short Entry: 5-min body entirely below ORB Low -> Buy {SHORT_TICKER}")
        print(f"[{self._get_timestamp_et()}] Max Trades: {MAX_TRADES_PER_DAY}")
        print(f"[{self._get_timestamp_et()}] Exit Strategy:")
        print(f"[{self._get_timestamp_et()}]   Stage 1: {HARD_STOP_PCT}% Hard Stop Loss")
        print(f"[{self._get_timestamp_et()}]   Stage 2: {PROFIT_TARGET_PCT}% Profit -> {TRAILING_STOP_PCT}% Trailing Stop")
        print(f"[{self._get_timestamp_et()}]   Stage 3: End of Day Exit at 2:30 PM CST (3:30 PM ET)")
        print(f"[{self._get_timestamp_et()}] Trading Window: 9:30 AM - 3:30 PM ET (6 hours)\n")
        
        # Mark that we're tracking ORB (only if before 9:45 AM)
        now_et = datetime.now(TIMEZONE_ET)
        if now_et.time() <= ORB_END:
            self.orb_tracking = True
            log_and_flush(f"[{self._get_timestamp_et()}] ORB tracking enabled - will track 9:30-9:45 AM range")
        else:
            self.orb_tracking = False
            self.orb_established = True  # Skip ORB since we're past the window
            log_and_flush(f"[{self._get_timestamp_et()}] ORB period already passed - no new trades today")
        
        # Subscribe to data streams - CRITICAL: Do this BEFORE connecting
        # All subscriptions are batched into a SINGLE websocket connection
        log_and_flush(f"[{self._get_timestamp_et()}] Setting up subscriptions...")
        
        # Subscribe to 1-minute bars for NVDA
        # - During 9:30-9:45: Tracks high/low to build ORB
        # - After 9:45: Aggregates into 5-min candles for breakout signals
        self.stream.subscribe_bars(self.handle_nvda_bar, MONITOR_TICKER)
        
        # Subscribe to NVDL and NVD trade streams (for real-time position monitoring)
        self.stream.subscribe_trades(self.handle_nvdl_trade, LONG_TICKER)
        self.stream.subscribe_trades(self.handle_nvd_trade, SHORT_TICKER)
        
        log_and_flush(f"[{self._get_timestamp_et()}] Subscribed to {MONITOR_TICKER} bars (ORB + entry signals)")
        log_and_flush(f"[{self._get_timestamp_et()}] Subscribed to {LONG_TICKER} trades (position monitoring)")
        log_and_flush(f"[{self._get_timestamp_et()}] Subscribed to {SHORT_TICKER} trades (position monitoring)")
        log_and_flush(f"[{self._get_timestamp_et()}] Tracking 9:30-9:45 AM opening range...\n")
        
        # Run the stream - use _run_forever() directly since we already have an event loop
        # The stream.run() method calls asyncio.run() which fails when a loop is already running
        log_and_flush(f"[{self._get_timestamp_et()}] Connecting to Alpaca websocket stream...")
        
        try:
            await self.stream._run_forever()
        except ValueError as e:
            if "connection limit exceeded" in str(e):
                log_and_flush(f"\n[{self._get_timestamp_et()}] !!!!! ERROR: CONNECTION LIMIT EXCEEDED !!!!!")
                log_and_flush(f"[{self._get_timestamp_et()}] This means another instance is already connected to Alpaca")
                log_and_flush(f"[{self._get_timestamp_et()}] ")
                log_and_flush(f"[{self._get_timestamp_et()}] Possible causes:")
                log_and_flush(f"[{self._get_timestamp_et()}]   1. Railway running multiple replicas (SET REPLICAS TO 1)")
                log_and_flush(f"[{self._get_timestamp_et()}]   2. Previous instance didn't close properly")
                log_and_flush(f"[{self._get_timestamp_et()}]   3. Another bot or service using same API keys")
                log_and_flush(f"[{self._get_timestamp_et()}] ")
                log_and_flush(f"[{self._get_timestamp_et()}] SOLUTION:")
                log_and_flush(f"[{self._get_timestamp_et()}]   1. Go to Railway dashboard")
                log_and_flush(f"[{self._get_timestamp_et()}]   2. Check Settings > Replicas = 1 (NOT more)")
                log_and_flush(f"[{self._get_timestamp_et()}]   3. Restart the service to kill all instances")
                log_and_flush(f"[{self._get_timestamp_et()}] ")
                log_and_flush(f"[{self._get_timestamp_et()}] Exiting current run - bot will retry in 30 seconds")
                release_connection_lock()
                await asyncio.sleep(30)
                return
            else:
                raise
        except Exception as e:
            log_and_flush(f"\n[{self._get_timestamp_et()}] !!!!! UNEXPECTED ERROR !!!!!")
            log_and_flush(f"[{self._get_timestamp_et()}] Error: {e}")
            log_and_flush(f"[{self._get_timestamp_et()}] Type: {type(e).__name__}")
            release_connection_lock()
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
            
            # Release the connection lock so future instances can connect
            release_connection_lock()


async def main():
    while True:
        # Stay alive overnight/weekends instead of exiting cleanly.
        await wait_until_session_start()

        now_et = datetime.now(TIMEZONE_ET)
        now_cst = datetime.now(TIMEZONE_CST)
        current_time_et = now_et.time()
        current_time_cst = now_cst.time()

        log_and_flush(f"[{now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}] NVDA Bot Starting...")
        log_and_flush(f"[{now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}] Current time ET: {current_time_et}")
        log_and_flush(f"[{now_cst.strftime('%Y-%m-%d %H:%M:%S %Z')}] Current time CST: {current_time_cst}")

        # Check if we missed the ORB window (after 9:45 AM ET)
        if current_time_et > time(9, 45):
            log_and_flush(f"[{now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}] WARNING: Starting after ORB period (9:30-9:45 AM ET)")
            log_and_flush(f"[{now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}] Bot will check for existing positions but won't enter new trades")
            log_and_flush(f"[{now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}] Reason: Cannot establish Opening Range after 9:45 AM")

        bot = NVDAOpeningRangeBot()
        await bot.run()

        # If we exited unexpectedly during active hours, pause briefly before retrying.
        now_et = datetime.now(TIMEZONE_ET)
        now_cst = datetime.now(TIMEZONE_CST)
        if now_et.weekday() < 5 and now_et.time() < END_OF_DAY_EXIT_ET and now_cst.time() < END_OF_DAY_EXIT:
            log_and_flush(f"[{now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}] Bot run exited during active hours. Retrying in 60 seconds.")
            await asyncio.sleep(60)


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
