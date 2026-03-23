# NVDA Trading Bot - Complete Guide

## 📊 Strategy Overview

**Name:** NVDA 15-Minute Opening Range Breakout (ORB)

**What it does:**
1. Tracks NVDA's first 15 minutes of trading (9:30-9:45 AM ET)
2. Records the high and low prices during this period (Opening Range)
3. After 9:45 AM, watches for 5-minute candle breakouts
4. Enters trades using 2x leveraged ETFs (NVDL or NVD)
5. Manages risk with hard stops and trailing stops
6. Exits at 2:30 PM CST (3:30 PM ET)

---

## 📈 Trade Entry Rules

### Long Entry (Buy NVDL)
- Wait for a 5-minute candle to close **entirely above** the ORB high
- Both the open AND close of the candle must be above ORB high
- Enter with market order on NVDL (2x Long ETF)

### Short Entry (Buy NVD)
- Wait for a 5-minute candle to close **entirely below** the ORB low
- Both the open AND close of the candle must be below ORB low
- Enter with market order on NVD (2x Short ETF)

### Position Sizing
- Fixed position size: $20,000
- Shares calculated as: $20,000 / ETF entry price
- 2x leverage built into ETF
- Maximum 1 trade per day

---

## 🛡️ Risk Management

### Stage 1: Hard Stop Loss (1.5%)
- Set immediately upon entry
- Managed by Alpaca automatically
- Example: Entry at $100 → Stop at $98.50
- Protects against large losses

### Stage 2: Profit Target (3%)
- When position reaches +3% profit ($600 on $20k)
- Hard stop is cancelled
- Upgraded to 1% trailing stop
- Lets winners run while protecting profits

### Stage 3: End of Day Exit (2:30 PM CST)
- Forced exit regardless of P&L
- Ensures no overnight positions
- Time: 2:30 PM CST / 3:30 PM ET
- 30 minutes before market close

---

## 🕐 Daily Schedule

| Time (ET) | Time (CST) | Activity |
|-----------|------------|----------|
| 9:00-9:30 AM | 8:00-8:30 AM | Pre-market: Close stale positions |
| 9:30-9:45 AM | 8:30-8:45 AM | Track Opening Range (ORB) |
| 9:45 AM | 8:45 AM | ORB established - start monitoring |
| 9:45 AM - 3:30 PM | 8:45 AM - 2:30 PM | Monitor for breakouts & manage position |
| 3:30 PM | 2:30 PM | End of day exit - close all positions |
| 3:30 PM - 9:30 AM | 2:30 PM - 8:30 AM | Bot idle, Railway restarts periodically |

**Total trading window: 6 hours (9:30 AM - 3:30 PM ET)**

---

## 💻 Configuration

### Files Structure
```
C:\Users\matth\
└── nvda_bot/
    ├── nvda_strategy.py (main bot code)
    ├── railway.toml (Railway config)
    └── requirements.txt (Python dependencies)
```

### Environment Variables (Railway)
- `ALPACA_API_KEY` - Your Alpaca API key
- `ALPACA_SECRET_KEY` - Your Alpaca secret key
- Paper trading mode: Enabled (hardcoded in bot)

### Railway Settings
- **Replicas:** 1 (MUST be 1, not more)
- **Restart Policy:** ON_FAILURE
- **Max Retries:** 10
- **Builder:** NIXPACKS

---

## 🚀 Deployment

### Initial Deployment
```bash
cd nvda_bot
git add .
git commit -m "Deploy NVDA bot to Railway"
git push origin main
```

Railway will automatically:
1. Detect the push
2. Build the Python environment
3. Install dependencies
4. Start `nvda_strategy.py`
5. Bot will check time and wait for market open

### Updates
```bash
# Make changes to nvda_strategy.py
git add nvda_bot/nvda_strategy.py
git commit -m "Update NVDA bot configuration"
git push origin main
```

Railway auto-deploys on every push to main branch.

---

## 📊 Monitoring

### Check Railway Logs For:

**✅ Successful startup:**
```
NVDA Bot Starting...
Connection successful - Account: PA3OVLQ636WP
Connection lock acquired
Checking for unexpected positions...
✅ No unexpected positions - ready to trade
✅ Ready to trade - ORB period active or upcoming
```

**✅ ORB establishment:**
```
===== OPENING RANGE ESTABLISHED =====
ORB High: $174.81
ORB Low: $174.64
ORB Range: $0.17
```

**✅ Trade entry:**
```
=== LONG BREAKOUT DETECTED ===
PLACING LONG ORDER
Ticker: NVDL
Shares: 1142
======================================================================
✅ TRADE OPENED - CONFIRMED WITH ALPACA ✅
======================================================================
Order ID: abc-123
Symbol: NVDL
Side: LONG
Shares Filled: 1142
Fill Price: $17.52
Position Value: $20,015.84
Stop Loss: $17.26 (-1.5%)
Status: FILLED
✅ POSITION VERIFIED IN ALPACA:
   Symbol: NVDL
   Qty: 1142.0
   Current Price: $17.52
   Market Value: $20,015.84
```

**✅ Clean exit:**
```
======================================================================
CLOSING ALL POSITIONS - END OF DAY EXIT at 2026-03-24 14:30:00 CDT
======================================================================
Symbol: NVDL
Side: long
Entry Price: $17.52
Exit Price: $17.89
Price Change: $0.37 (+2.11%)
Shares: 1142
Market Value: $20,434.38
Final P&L: $422.54 (+2.11%)

Closing position...
✅ Close order submitted to Alpaca
✅ POSITION CLOSED - VERIFIED WITH ALPACA
   NVDL position no longer exists in account

✅ No pending orders to cancel
======================================================================

[2026-03-24 15:30:00 EDT] Websocket closed successfully
[INFO] Connection lock released
```

### Red Flags (Should NOT appear):

**❌ Unexpected position detected:**
```
⚠️  UNEXPECTED POSITION DETECTED - BOT STOPPING ⚠️
======================================================================
Symbol: NVDL
Shares: 1142
Current Price: $17.52
Market Value: $20,015.84
Unrealized P&L: $422.54

POSSIBLE CAUSES:
  1. Position from previous day didn't close (check yesterday's logs)
  2. Manual trade entered in Alpaca dashboard
  3. Bot crashed before closing position
  4. Another bot/strategy using same account
```
**Solution:** 
1. Go to Alpaca dashboard immediately
2. Check the position - is it yours? From yesterday?
3. Review yesterday's logs for close confirmations
4. Close position manually in Alpaca if it's an error
5. Railway will restart bot automatically after you fix it

**❌ Connection errors:**
```
connection limit exceeded
HTTP 429
```
**Solution:** Check Railway replicas = 1, restart service (should not happen with single bot)

**❌ Late start:**
```
WARNING: Starting after ORB period (9:30-9:45 AM ET)
Cannot establish Opening Range - no new trades today
```
**Solution:** Bot started too late, will retry tomorrow

**❌ Multiple instances:**
```
ERROR: Another instance holds the connection lock
```
**Solution:** Railway running multiple replicas, set to 1

---

## 🔧 Protection Features

### 1. Connection Lock System
- Prevents multiple bot instances from running
- Lock file: `/tmp/nvda_bot_connection.lock`
- Automatic stale lock cleanup (after 10 minutes)
- Ensures only ONE websocket connection at a time

### 2. Exponential Backoff
- Prevents restart storms if Railway glitches
- Delays increase: 5s → 10s → 20s → 40s → 60s (max)
- Automatically resets after 5 minutes of stable operation
- Protects against Alpaca API rate limits

### 3. Unexpected Position Detection
- Detects positions that shouldn't exist (leftover from previous day)
- **STOPS THE BOT** if unexpected position found
- Logs full position details and requires manual review
- Prevents auto-closing positions that might be intentional

### 4. Time Window Enforcement
- Refuses to trade if starting after ORB period
- Exits at 2:30 PM CST automatically
- Won't connect to websocket outside trading hours
- Prevents wasted Railway cycles

---

## 🧪 Testing

### Paper Trading Mode
Bot runs in paper trading mode (no real money at risk):
- Uses Alpaca Paper account
- Real-time market data
- Simulated order fills
- Full order management features

### Manual Testing
1. Check Railway logs at 9:30 AM ET
2. Verify ORB is established at 9:45 AM
3. Monitor for breakout signals
4. Verify position entry/exit logging
5. Confirm clean exit at 3:30 PM ET

---

## 📞 Troubleshooting

### Bot isn't trading
**Check:**
1. Did bot start before 9:45 AM ET?
2. Was ORB established successfully?
3. Were there any breakout signals?
4. Is max trades per day = 1 already hit?

### Connection errors
**Check:**
1. Railway replicas = 1 (not more)
2. No other bots using same API keys
3. Alpaca API status (alpaca.markets/status)
4. Check lock files in logs

### Bot exits immediately
**Check:**
1. Current time - is it outside trading window?
2. Railway logs for time check messages
3. Market holiday calendar
4. Weekend (Saturday/Sunday)

### Position not closing at exit time
**Check:**
1. Bot logs for "END OF DAY EXIT" message
2. Alpaca dashboard for open positions
3. Railway logs for errors during close
4. Time zone settings (CST vs ET)

---

## 📋 Daily Checklist

### Before Market Open (9:00 AM ET)
- [ ] Check Railway service is running
- [ ] **CRITICAL:** Verify NO positions exist in Alpaca dashboard (all should be closed from previous day)
- [ ] Review previous day's logs to confirm clean exit at 2:30 PM CST
- [ ] If unexpected position found, bot will STOP and alert you

### During Trading (9:30 AM - 3:30 PM ET)
- [ ] Monitor Railway logs for ORB establishment (9:45 AM)
- [ ] Watch for breakout signals and entries
- [ ] Check position status if trade entered
- [ ] Verify stop loss orders are active

### After Market Close (3:30 PM+ ET)
- [ ] Confirm all positions closed
- [ ] Review trade P&L in Alpaca dashboard
- [ ] Check Railway logs for clean exit
- [ ] Note any issues for tomorrow

---

## 💰 Performance Tracking

### Key Metrics
- Win rate (% of profitable trades)
- Average profit on winners
- Average loss on losers
- Max drawdown per trade
- Days traded vs. days with signals

### Example Trade
```
Entry: NVDL @ $17.52 (1142 shares)
Stop: $17.26 (-1.5%)
Target: $18.04 (+3%)
Exit: $17.89 (trailing stop hit)
P&L: +$422.54 (+2.11%)
Position size: $20,008
```

---

## 🎯 Success Criteria

**Bot is working correctly if:**
1. ✅ Starts before 9:30 AM ET
2. ✅ Establishes ORB successfully at 9:45 AM
3. ✅ Enters trades on valid breakouts only
4. ✅ Manages stops correctly (hard → trailing)
5. ✅ Exits all positions by 2:30 PM CST
6. ✅ No "connection limit exceeded" errors
7. ✅ Logs are clear and informative

**Expected results:**
- Not every day will have a trade (depends on breakouts)
- Some trades will hit stops (normal)
- Overall: Positive expectancy over time

---

## 🔄 Updates & Maintenance

### Making Changes
1. Edit `nvda_bot/nvda_strategy.py`
2. Test locally if possible
3. Commit changes to git
4. Push to Railway (auto-deploys)
5. Monitor first hour of next trading day

### Configuration Changes
**Modify constants at top of file:**
- `HARD_STOP_PCT` - Stop loss percentage
- `PROFIT_TARGET_PCT` - When to activate trailing stop
- `TRAILING_STOP_PCT` - Trailing stop percentage
- `END_OF_DAY_EXIT` - Exit time
- `MAX_TRADES_PER_DAY` - Trade limit

### Safety Notes
- Always test in paper trading first
- One change at a time
- Monitor for at least 1 week before another change
- Keep old code commented if unsure

---

## 📁 Important Files

- `nvda_bot/nvda_strategy.py` - Main bot code
- `nvda_bot/railway.toml` - Railway configuration
- `nvda_bot/requirements.txt` - Python dependencies
- `.env` - Local environment variables (not in git)
- `NVDA_BOT_GUIDE.md` - This file

---

## 🎓 Strategy Background

**Why Opening Range Breakout?**
- First 15 minutes show institutional intent
- Breakouts often lead to sustained moves
- Clear entry rules (no discretion)
- Defined risk/reward

**Why 2x Leveraged ETFs?**
- Amplifies NVDA movements
- No margin requirements
- Can't lose more than position size
- NVDL/NVD more liquid than NVDA options

**Why Exit at 2:30 PM CST?**
- Avoids end-of-day volatility (3:30-4:00 PM)
- 6-hour trading window is sufficient
- Reduces overnight gap risk
- Clean daily reset

---

## ✅ Current Status

**Version:** Single-bot setup (March 23, 2026)
**Status:** Active
**Mode:** Paper trading
**Platform:** Railway (auto-deploy)
**Trading Window:** 9:30 AM - 3:30 PM ET
**Connection Locks:** Enabled
**Exponential Backoff:** Enabled
**Stale Position Cleanup:** Enabled

---

Last updated: March 23, 2026
