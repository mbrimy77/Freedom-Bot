# NVDA Bot Rewrite - March 19, 2026

## Problem Solved

### Issue 1: Basic Subscription Limitation
**Old Approach:** ❌ Tried to fetch historical bar data at 9:45 AM
- Basic plan only allows "latest 15 minutes" of historical data
- At 9:45 AM, we can't access 9:30-9:45 data (already too old)
- Error: Subscription doesn't permit querying recent 1-minute data

**New Approach:** ✅ Track ORB in real-time using live stream
- No historical data API calls needed
- Uses 1-minute live bars from 9:30-9:45 AM
- Builds ORB high/low as bars arrive in real-time
- Works perfectly with Basic subscription

---

### Issue 2: Incorrect Entry Logic
**Old Approach:** ❌ Only checked if 5-min close was above/below ORB
- Didn't verify the candle body was entirely above/below
- Could trigger false breakouts

**New Approach:** ✅ Checks if BOTH open AND close are above/below ORB
- LONG: `candle_open > ORB_high` AND `candle_close > ORB_high`
- SHORT: `candle_open < ORB_low` AND `candle_close < ORB_low`
- Ensures the entire candle body cleared the level
- More conservative and accurate

---

## How It Works Now

### Phase 1: Opening Range (9:30-9:45 AM ET)

1. **Bot starts at 9:30 AM**
2. **Subscribes to 1-minute NVDA bars** (live stream)
3. **Tracks running high/low:**
   ```
   9:30 bar: high=$142.50, low=$141.80
   → ORB_high=$142.50, ORB_low=$141.80
   
   9:31 bar: high=$142.75, low=$142.00
   → ORB_high=$142.75 (new), ORB_low=$141.80 (no change)
   
   ... continues until 9:45 AM
   ```
4. **At 9:45 AM: ORB Complete**
   - Logs final ORB_high and ORB_low
   - Switches to Phase 2

---

### Phase 2: Entry Signals (After 9:45 AM)

1. **Aggregates 1-min bars into 5-min candles**
   - 9:45-9:49 → First 5-min candle
   - 9:50-9:54 → Second 5-min candle
   - etc.

2. **When each 5-min candle completes:**
   - Checks if body is entirely above ORB high (LONG)
   - Checks if body is entirely below ORB low (SHORT)

3. **Entry Logic:**

**LONG Signal (Buy NVDL):**
```
IF candle_open > ORB_high AND candle_close > ORB_high:
    → Body entirely above ORB high
    → BUY NVDL (2x Long)
```

**SHORT Signal (Buy NVD):**
```
IF candle_open < ORB_low AND candle_close < ORB_low:
    → Body entirely below ORB low
    → BUY NVD (2x Short)
```

---

## Example Scenarios

### Scenario 1: Valid LONG Breakout ✅
```
ORB High: $142.00

5-min Candle:
  Open:  $142.25  ← Above ORB high ✓
  High:  $142.80
  Low:   $142.10
  Close: $142.60  ← Above ORB high ✓

RESULT: Body entirely above $142.00 → BUY NVDL
```

### Scenario 2: Invalid LONG (Candle body not entirely above) ❌
```
ORB High: $142.00

5-min Candle:
  Open:  $141.80  ← Below ORB high ✗
  High:  $142.50
  Low:   $141.50
  Close: $142.20  ← Above ORB high ✓

RESULT: Body crosses ORB level → NO SIGNAL (wait for cleaner breakout)
```

### Scenario 3: Valid SHORT Breakout ✅
```
ORB Low: $140.50

5-min Candle:
  Open:  $140.30  ← Below ORB low ✓
  High:  $140.40
  Low:   $139.90
  Close: $140.10  ← Below ORB low ✓

RESULT: Body entirely below $140.50 → BUY NVD
```

---

## Key Benefits

### 1. Works with Basic Subscription ✅
- No historical data API calls
- Uses only live streaming (included in Basic plan)
- No "latest 15 minutes" restriction issues

### 2. More Accurate Entries ✅
- Only trades when body CLEARS the level
- Filters out weak breakouts
- Reduces false signals

### 3. Cleaner Code ✅
- No retry logic for failed API calls
- No complex error handling
- Real-time tracking is simpler

### 4. No Data Lag ✅
- Live stream is instant
- Don't have to wait for data availability
- More reliable execution

---

## What You'll See in Logs

### Phase 1 (9:30-9:45 AM):
```
[2026-03-19 09:30:00 EDT] NVDA 15-MIN OPENING RANGE BREAKOUT BOT STARTED
[2026-03-19 09:30:00 EDT] Market is open - ready to trade
[2026-03-19 09:30:00 EDT] Tracking 9:30-9:45 AM opening range...

(15 minutes of tracking...)

[2026-03-19 09:45:01 EDT] ===== OPENING RANGE ESTABLISHED =====
[2026-03-19 09:45:01 EDT] Time: 9:30-9:45 AM ET
[2026-03-19 09:45:01 EDT] ORB High: $142.75
[2026-03-19 09:45:01 EDT] ORB Low: $140.50
[2026-03-19 09:45:01 EDT] ORB Range: $2.25
[2026-03-19 09:45:01 EDT] =====================================

[2026-03-19 09:45:01 EDT] Now monitoring 5-minute candles for breakouts...
```

### Phase 2 (After 9:45 AM):
```
[2026-03-19 09:49:59 EDT] 5-min Candle Complete: O=$141.90 H=$142.10 L=$141.75 C=$141.95
[2026-03-19 09:49:59 EDT] No breakout (ORB High: $142.75, ORB Low: $140.50)

[2026-03-19 09:54:59 EDT] 5-min Candle Complete: O=$142.80 H=$143.00 L=$142.70 C=$142.90

[2026-03-19 09:54:59 EDT] === LONG BREAKOUT DETECTED ===
[2026-03-19 09:54:59 EDT] Candle Body: Open=$142.80, Close=$142.90
[2026-03-19 09:54:59 EDT] ORB High: $142.75
[2026-03-19 09:54:59 EDT] Body entirely above ORB High - LONG signal confirmed!
[2026-03-19 09:54:59 EDT] Placing LONG trade for NVDL...
```

---

## Files Changed

- `nvda_bot/nvda_strategy.py` - Complete rewrite of ORB and entry logic

---

## Deploy to Railway

1. Go to Railway Dashboard
2. Click "NVDA-Bot" service
3. Go to "Deployments"
4. Click "Redeploy" (or it may auto-deploy from GitHub)
5. Watch logs to confirm proper startup

---

## Summary

✅ **Basic subscription compatible** (no historical data calls)
✅ **Correct entry logic** (body must be entirely above/below ORB)
✅ **Cleaner, more reliable** code
✅ **Real-time tracking** (no data lag)

**You're all set for tomorrow's trading!** 🚀
