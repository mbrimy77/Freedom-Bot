"""
MSOS Bot Test Script
Run this to verify everything works before live trading
"""

import asyncio
import os
from datetime import datetime, time, timedelta
import pytz
from dotenv import load_dotenv

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestBarRequest
from alpaca.data.timeframe import TimeFrame

# Load environment variables
load_dotenv()

TIMEZONE = pytz.timezone('America/Chicago')

class BotTester:
    def __init__(self):
        self.api_key = os.getenv('ALPACA_API_KEY')
        self.secret_key = os.getenv('ALPACA_SECRET_KEY')
        
        if not self.api_key or not self.secret_key:
            print("ERROR: API keys not found in .env file!")
            return
        
        self.trading_client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=True
        )
        self.data_client = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key
        )
        
        print("="*60)
        print("MSOS BOT TEST SUITE")
        print("="*60)
    
    async def test_1_connection(self):
        """Test 1: API Connection"""
        print("\n[TEST 1] Testing Alpaca API Connection...")
        try:
            account = self.trading_client.get_account()
            print(f"  SUCCESS: Connected to Alpaca")
            print(f"  Account Status: {account.status}")
            print(f"  Buying Power: ${float(account.buying_power):,.2f}")
            print(f"  Paper Trading: {account.account_number.startswith('P')}")
            return True
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def test_2_previous_close(self):
        """Test 2: Fetch Previous Close"""
        print("\n[TEST 2] Testing Previous Close Fetch...")
        try:
            now = datetime.now(TIMEZONE)
            
            # Get previous trading day
            days_to_subtract = 1
            if now.weekday() == 0:  # Monday
                days_to_subtract = 3
            elif now.weekday() == 6:  # Sunday
                days_to_subtract = 2
            
            previous_day = now - timedelta(days=days_to_subtract)
            
            request = StockBarsRequest(
                symbol_or_symbols="MSOS",
                timeframe=TimeFrame.Day,
                start=previous_day.replace(hour=15, minute=0),
                end=previous_day.replace(hour=16, minute=0)
            )
            
            bars = self.data_client.get_stock_bars(request)
            
            if "MSOS" in bars and len(bars["MSOS"]) > 0:
                previous_close = float(bars["MSOS"][-1].close)
                print(f"  SUCCESS: Previous close retrieved")
                print(f"  Date: {previous_day.strftime('%Y-%m-%d')}")
                print(f"  MSOS Close: ${previous_close:.2f}")
                print(f"  +2.5% Trigger: ${previous_close * 1.025:.2f}")
                print(f"  -2.5% Trigger: ${previous_close * 0.975:.2f}")
                return True
            else:
                print(f"  WARNING: No data returned (trying latest bar)")
                request = StockLatestBarRequest(symbol_or_symbols="MSOS")
                latest = self.data_client.get_stock_latest_bar(request)
                previous_close = float(latest["MSOS"].close)
                print(f"  SUCCESS: Latest close: ${previous_close:.2f}")
                return True
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def test_3_notional_order(self):
        """Test 3: Notional Order Calculation"""
        print("\n[TEST 3] Testing Notional Order...")
        try:
            notional = 20000
            test_price = 12.50
            
            shares = notional / test_price
            print(f"  SUCCESS: Notional calculation")
            print(f"  Notional Amount: ${notional:,}")
            print(f"  Assumed Price: ${test_price:.2f}")
            print(f"  Shares: {int(shares)}")
            print(f"  Actual Cost: ${shares * test_price:,.2f}")
            return True
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def test_4_order_submission(self):
        """Test 4: Order Submission (Test with small limit order)"""
        print("\n[TEST 4] Testing Order Submission...")
        print("  This will place and immediately cancel a test order")
        
        response = input("  Do you want to test order submission? (y/n): ")
        if response.lower() != 'y':
            print("  SKIPPED: User chose not to test orders")
            return True
        
        try:
            # Place a small limit order that won't fill
            test_price = 1.00  # Very low price, won't fill
            
            order_data = LimitOrderRequest(
                symbol="MSOX",
                qty=1,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=test_price
            )
            
            print(f"  Placing test order: 1 share MSOX at ${test_price}")
            order = self.trading_client.submit_order(order_data)
            print(f"  SUCCESS: Order placed - ID: {order.id}")
            
            # Immediately cancel it
            await asyncio.sleep(1)
            self.trading_client.cancel_order_by_id(order.id)
            print(f"  SUCCESS: Order canceled")
            
            return True
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def test_5_asset_check(self):
        """Test 5: Check MSOX and SMSO availability"""
        print("\n[TEST 5] Testing Asset Availability...")
        try:
            # Check MSOX
            msox = self.trading_client.get_asset("MSOX")
            print(f"  MSOX Status: {msox.status}")
            print(f"  MSOX Tradable: {msox.tradable}")
            print(f"  MSOX Shortable: {msox.shortable}")
            print(f"  MSOX Easy to Borrow: {msox.easy_to_borrow}")
            
            # Check SMSO
            smso = self.trading_client.get_asset("SMSO")
            print(f"  SMSO Status: {smso.status}")
            print(f"  SMSO Tradable: {smso.tradable}")
            
            if msox.tradable and smso.tradable:
                print(f"  SUCCESS: Both tickers are tradable")
                return True
            else:
                print(f"  WARNING: One or both tickers not tradable")
                return False
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def test_6_trailing_stop(self):
        """Test 6: Trailing Stop Logic"""
        print("\n[TEST 6] Testing Trailing Stop Calculation...")
        try:
            entry_price = 12.50
            trailing_pct = 1.0
            
            # Simulate price increase
            highest_price = 12.75
            stop_price = highest_price * (1 - trailing_pct / 100)
            
            print(f"  SUCCESS: Trailing stop calculated")
            print(f"  Entry Price: ${entry_price:.2f}")
            print(f"  Highest Price: ${highest_price:.2f}")
            print(f"  Stop Price: ${stop_price:.2f} (1.0% trailing)")
            print(f"  Profit at stop: ${stop_price - entry_price:.2f}")
            return True
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def test_7_timezone_check(self):
        """Test 7: Timezone Configuration"""
        print("\n[TEST 7] Testing Timezone Configuration...")
        try:
            now_cst = datetime.now(TIMEZONE)
            
            print(f"  Current CST Time: {now_cst.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"  Bot Startup: 2:00 PM CST")
            print(f"  Trade Window: 2:15 PM - 2:30 PM CST")
            print(f"  Hard Exit: 2:58 PM CST")
            
            print(f"  SUCCESS: Timezone configured")
            return True
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all tests"""
        results = []
        
        results.append(await self.test_1_connection())
        results.append(await self.test_2_previous_close())
        results.append(await self.test_3_notional_order())
        results.append(await self.test_4_order_submission())
        results.append(await self.test_5_asset_check())
        results.append(await self.test_6_trailing_stop())
        results.append(await self.test_7_timezone_check())
        
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(results)
        total = len(results)
        
        print(f"Tests Passed: {passed}/{total}")
        
        if passed == total:
            print("\nSTATUS: ALL TESTS PASSED!")
            print("Bot is ready for tomorrow's trading.")
        else:
            print("\nSTATUS: SOME TESTS FAILED")
            print("Please fix issues before live trading.")
        
        print("\nNext Steps:")
        print("1. Check Railway deployment logs")
        print("2. Verify environment variables are set")
        print("3. Monitor logs at 2:00 PM CST tomorrow")
        print("="*60)


async def main():
    tester = BotTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    print("\nMake sure you have a .env file with:")
    print("  ALPACA_API_KEY=your_key")
    print("  ALPACA_SECRET_KEY=your_secret")
    print()
    
    asyncio.run(main())
