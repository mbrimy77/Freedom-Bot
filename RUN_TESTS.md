# How to Run Bot Tests

## 🧪 Test Your Bots Before Tomorrow

I've created comprehensive test scripts to verify everything works.

---

## 📋 **What the Tests Check:**

### **NVDA Bot Tests:**
1. ✅ API Connection to Alpaca
2. ✅ Market data access (NVDA historical data)
3. ✅ Opening Range Breakout calculation
4. ✅ Position sizing (shares for $300 risk)
5. ✅ Order submission & cancellation
6. ✅ NVDL and NVD tradability
7. ✅ Timezone configuration

### **MSOS Bot Tests:**
1. ✅ API Connection to Alpaca
2. ✅ Previous close fetch
3. ✅ Notional order calculation ($20k)
4. ✅ Order submission & cancellation
5. ✅ MSOX and SMSO tradability
6. ✅ Trailing stop logic
7. ✅ Timezone configuration

---

## 🚀 **How to Run Tests:**

### **Option 1: Run Locally (Recommended)**

**Test NVDA Bot:**
```bash
cd nvda_bot
python test_bot.py
```

**Test MSOS Bot:**
```bash
cd msos_bot
python test_bot.py
```

### **Option 2: Quick Connection Test**

Just test if Alpaca API is working:
```bash
cd nvda_bot
python -c "from test_bot import BotTester; import asyncio; asyncio.run(BotTester().test_1_connection())"
```

---

## 📊 **What You'll See:**

```
============================================================
NVDA BOT TEST SUITE
============================================================

[TEST 1] Testing Alpaca API Connection...
  SUCCESS: Connected to Alpaca
  Account Status: ACTIVE
  Buying Power: $100,000.00
  Paper Trading: True

[TEST 2] Testing Market Data Access...
  SUCCESS: Retrieved 15 bars for NVDA
  Latest Price: $875.50

[TEST 3] Testing ORB Calculation...
  SUCCESS: ORB calculated from 15 bars
  Date: 2026-03-18
  ORB High: $876.20
  ORB Low: $871.50
  ORB Range: $4.70

[TEST 4] Testing Position Sizing...
  SUCCESS: Position sizing calculated
  Entry Price: $43.50
  Shares: 229
  Notional Value: $9,961.50
  Expected Max Loss: $298.85

[TEST 5] Testing Order Submission...
  Do you want to test order submission? (y/n): y
  Placing test order: 1 share NVDL at $1.0
  SUCCESS: Order placed - ID: abc123
  SUCCESS: Order canceled

[TEST 6] Testing Asset Availability...
  NVDL Status: active
  NVDL Tradable: True
  NVDL Marginable: True
  NVD Status: active
  NVD Tradable: True
  NVD Marginable: True
  SUCCESS: Both ETFs are tradable

[TEST 7] Testing Timezone Configuration...
  Current ET Time: 2026-03-18 20:30:00 EDT
  Current CST Time: 2026-03-18 19:30:00 CST
  Market Open (ET): 9:30 AM
  Golden Gap Exit (CST): 2:00 PM
  SUCCESS: Timezone configuration correct

============================================================
TEST SUMMARY
============================================================
Tests Passed: 7/7

STATUS: ALL TESTS PASSED!
Bot is ready for tomorrow's trading.

Next Steps:
1. Check Railway deployment logs
2. Verify environment variables are set
3. Monitor logs at 9:30 AM ET tomorrow
============================================================
```

---

## ⚠️ **If Tests Fail:**

### **"API keys not found"**
```bash
# Create .env file in the bot folder
cd nvda_bot  # or msos_bot
echo "ALPACA_API_KEY=your_key_here" > .env
echo "ALPACA_SECRET_KEY=your_secret_here" >> .env
```

### **"Connection failed"**
- Check your internet connection
- Verify API keys are correct
- Check Alpaca status: https://status.alpaca.markets

### **"Asset not tradable"**
- NVDL/NVD or MSOX/SMSO might be halted
- Check Alpaca dashboard
- Usually resolves when market opens

### **"No market data"**
- Normal if running when market is closed
- Test will skip or use cached data
- Not a blocker for tomorrow

---

## 🔒 **About Order Testing:**

The script will ask:
```
Do you want to test order submission? (y/n):
```

**What it does:**
- Places a LIMIT order at $1.00 (way below market price)
- Order won't fill (by design)
- Immediately cancels the order
- Tests Alpaca API order functionality

**Safe to run?** YES - It's a test order that won't execute

**Skip it?** You can skip if you want - tests API only

---

## 📝 **Test Checklist:**

Before tomorrow, make sure:

- [ ] Run `python test_bot.py` in nvda_bot folder
- [ ] All 7 tests pass for NVDA bot
- [ ] Run `python test_bot.py` in msos_bot folder
- [ ] All 7 tests pass for MSOS bot
- [ ] Check Railway has both bots deployed
- [ ] Verify environment variables in Railway
- [ ] Check Alpaca account has $20k+ buying power

---

## 🎯 **What If Everything Passes?**

✅ Your bots are ready!  
✅ API connection works  
✅ Market data access works  
✅ Order functionality works  
✅ Logic is sound  

**Tomorrow morning:**
- 9:30 AM ET: Check NVDA bot logs
- 2:00 PM CST: Check MSOS bot logs
- Watch for "Opening Range Established" and "PLACING ORDER"

---

## 💡 **Pro Tips:**

1. **Run tests NOW** - Don't wait until tomorrow morning
2. **Save test output** - Screenshot or copy the results
3. **Test both bots** - NVDA and MSOS
4. **Check Railway** - Make sure both are deployed
5. **Monitor tomorrow** - Keep Railway logs open

---

## 🆘 **Need Help?**

If any test fails:
1. Read the error message
2. Check the "If Tests Fail" section above
3. Verify your .env file has correct API keys
4. Make sure you're connected to internet

**Common issues:**
- Missing .env file → Create it with API keys
- Wrong directory → cd into nvda_bot or msos_bot first
- Market closed → Some tests use historical data (that's ok)

---

## ✅ **Final Pre-Launch Checklist:**

1. [ ] Both test suites pass (NVDA + MSOS)
2. [ ] Railway shows both services deployed
3. [ ] Environment variables set in Railway
4. [ ] Alpaca account active with funds
5. [ ] Understand the logging output
6. [ ] Know where to check logs tomorrow

**You're ready for tomorrow! 🚀**
