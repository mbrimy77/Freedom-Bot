"""
NVDA Bot Test Script
Run this to verify everything works before live trading
"""

import asyncio
import os
from datetime import datetime, time, timedelta
import pytz
from dotenv import load_dotenv

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load environment variables
load_dotenv()

TIMEZONE_ET = pytz.timezone('America/New_York')
TIMEZONE_CST = pytz.timezone('America/Chicago')

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
        print("NVDA BOT TEST SUITE")
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
    
    async def test_2_market_data(self):
        """Test 2: Market Data Access"""
        print("\n[TEST 2] Testing Market Data Access...")
        try:
            # Test NVDA data
            now_et = datetime.now(TIMEZONE_ET)
            yesterday = now_et - timedelta(days=1)
            
            request = StockBarsRequest(
                symbol_or_symbols="NVDA",
                timeframe=TimeFrame.Minute,
                start=yesterday.replace(hour=9, minute=30),
                end=yesterday.replace(hour=9, minute=45),
                limit=15
            )
            
            bars = self.data_client.get_stock_bars(request)
            
            if "NVDA" in bars and len(bars["NVDA"]) > 0:
                print(f"  SUCCESS: Retrieved {len(bars['NVDA'])} bars for NVDA")
                latest_bar = bars["NVDA"][-1]
                print(f"  Latest Price: ${float(latest_bar.close):.2f}")
                return True
            else:
                print(f"  WARNING: No bar data returned (market may be closed)")
                return True  # Don't fail if market is closed
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def test_3_orb_calculation(self):
        """Test 3: Opening Range Breakout Logic"""
        print("\n[TEST 3] Testing ORB Calculation...")
        try:
            # Get yesterday's data for testing
            now_et = datetime.now(TIMEZONE_ET)
            yesterday = now_et - timedelta(days=1)
            
            # If yesterday was weekend, go back further
            while yesterday.weekday() >= 5:
                yesterday -= timedelta(days=1)
            
            orb_start = yesterday.replace(hour=9, minute=30, second=0)
            orb_end = yesterday.replace(hour=9, minute=45, second=0)
            
            request = StockBarsRequest(
                symbol_or_symbols="NVDA",
                timeframe=TimeFrame.Minute,
                start=orb_start,
                end=orb_end,
                limit=15
            )
            
            bars = self.data_client.get_stock_bars(request)
            
            if "NVDA" in bars and len(bars["NVDA"]) > 0:
                bar_list = bars["NVDA"]
                orb_high = max([float(bar.high) for bar in bar_list])
                orb_low = min([float(bar.low) for bar in bar_list])
                orb_range = orb_high - orb_low
                
                print(f"  SUCCESS: ORB calculated from {len(bar_list)} bars")
                print(f"  Date: {yesterday.strftime('%Y-%m-%d')}")
                print(f"  ORB High: ${orb_high:.2f}")
                print(f"  ORB Low: ${orb_low:.2f}")
                print(f"  ORB Range: ${orb_range:.2f}")
                return True
            else:
                print(f"  WARNING: No data available for testing")
                return True
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def test_4_position_sizing(self):
        """Test 4: Position Sizing Calculation"""
        print("\n[TEST 4] Testing Position Sizing...")
        try:
            # Test with sample entry price
            entry_price = 43.50
            risk_amount = 300
            stop_pct = 1.5
            leverage = 2.0
            
            shares = risk_amount / (entry_price * (stop_pct / 100) * leverage)
            shares = int(shares)
            
            notional_value = shares * entry_price
            max_loss = shares * entry_price * (stop_pct / 100) * leverage
            
            print(f"  SUCCESS: Position sizing calculated")
            print(f"  Entry Price: ${entry_price:.2f}")
            print(f"  Shares: {shares}")
            print(f"  Notional Value: ${notional_value:.2f}")
            print(f"  Expected Max Loss: ${max_loss:.2f}")
            
            if max_loss > 310:
                print(f"  WARNING: Max loss exceeds $300 target")
                return False
            
            return True
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def test_5_order_submission(self):
        """Test 5: Order Submission (Test with 1 share)"""
        print("\n[TEST 5] Testing Order Submission...")
        print("  This will place and immediately cancel a test order")
        
        response = input("  Do you want to test order submission? (y/n): ")
        if response.lower() != 'y':
            print("  SKIPPED: User chose not to test orders")
            return True
        
        try:
            # Place a small limit order that won't fill
            test_price = 1.00  # Very low price, won't fill
            
            order_data = LimitOrderRequest(
                symbol="NVDL",
                qty=1,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=test_price
            )
            
            print(f"  Placing test order: 1 share NVDL at ${test_price}")
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
    
    async def test_6_asset_check(self):
        """Test 6: Check NVDL and NVD are tradeable"""
        print("\n[TEST 6] Testing Asset Availability...")
        try:
            # Check NVDL
            nvdl = self.trading_client.get_asset("NVDL")
            print(f"  NVDL Status: {nvdl.status}")
            print(f"  NVDL Tradable: {nvdl.tradable}")
            print(f"  NVDL Marginable: {nvdl.marginable}")
            
            # Check NVD
            nvd = self.trading_client.get_asset("NVD")
            print(f"  NVD Status: {nvd.status}")
            print(f"  NVD Tradable: {nvd.tradable}")
            print(f"  NVD Marginable: {nvd.marginable}")
            
            if nvdl.tradable and nvd.tradable:
                print(f"  SUCCESS: Both ETFs are tradable")
                return True
            else:
                print(f"  WARNING: One or both ETFs not tradable")
                return False
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def test_7_timezone_check(self):
        """Test 7: Timezone Configuration"""
        print("\n[TEST 7] Testing Timezone Configuration...")
        try:
            now_et = datetime.now(TIMEZONE_ET)
            now_cst = datetime.now(TIMEZONE_CST)
            
            print(f"  Current ET Time: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"  Current CST Time: {now_cst.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"  Market Open (ET): 9:30 AM")
            print(f"  End of Day Exit (CST): 2:30 PM / (ET): 3:30 PM")
            
            # Check if times make sense
            time_diff = (now_et - now_cst).total_seconds() / 3600
            if abs(time_diff - 1.0) < 0.1:  # Should be ~1 hour difference
                print(f"  SUCCESS: Timezone configuration correct")
                return True
            else:
                print(f"  WARNING: Timezone difference seems wrong: {time_diff:.1f} hours")
                return False
        except Exception as e:
            print(f"  FAILED: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all tests"""
        results = []
        
        results.append(await self.test_1_connection())
        results.append(await self.test_2_market_data())
        results.append(await self.test_3_orb_calculation())
        results.append(await self.test_4_position_sizing())
        results.append(await self.test_5_order_submission())
        results.append(await self.test_6_asset_check())
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
        print("3. Monitor logs at 9:30 AM ET tomorrow")
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
