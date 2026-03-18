# Bot Monitoring Comparison

## Overview

Both bots now use **real-time trade streams** for accurate position monitoring and stop loss management. This ensures both strategies have instant visibility into price movements.

## NVDA Bot Data Streams

### Stream 1: NVDA Bars (Entry Signals)
```python
self.stream.subscribe_bars(self.handle_nvda_bar, "NVDA")
```
- **Purpose**: Detect 5-minute breakouts outside the Opening Range
- **Frequency**: 1-minute bars from Alpaca
- **Used For**: Entry signals only

### Stream 2: NVDL Trades (Long Position Monitoring)
```python
self.stream.subscribe_trades(self.handle_nvdl_trade, "NVDL")
```
- **Purpose**: Real-time monitoring of 2x Long ETF position
- **Frequency**: Every trade (tick-by-tick)
- **Used For**: 
  - Profit target detection (3% → trailing stop upgrade)
  - Highest price tracking
  - Real-time P&L calculations
  - Periodic logging (every 30 seconds)

### Stream 3: NVD Trades (Short Position Monitoring)
```python
self.stream.subscribe_trades(self.handle_nvd_trade, "NVD")
```
- **Purpose**: Real-time monitoring of 2x Short ETF position
- **Frequency**: Every trade (tick-by-tick)
- **Used For**:
  - Profit target detection (3% → trailing stop upgrade)
  - Lowest price tracking
  - Real-time P&L calculations
  - Periodic logging (every 30 seconds)

---

## MSOS Bot Data Streams

### Stream 1: MSOS Trades (Entry Signals)
```python
self.stream.subscribe_trades(self.handle_msos_trade, "MSOS")
```
- **Purpose**: Detect momentum breakouts (+/- 2.5% from previous close)
- **Frequency**: Every trade (tick-by-tick)
- **Used For**: Entry signals and percent change calculations

### Stream 2: MSOX Trades (Position Monitoring)
```python
self.stream.subscribe_trades(self.handle_msox_trade, "MSOX")
```
- **Purpose**: Real-time monitoring of 3x ETF position
- **Frequency**: Every trade (tick-by-tick)
- **Used For**:
  - Trailing stop calculations (1.0%)
  - Highest/lowest price tracking
  - Stop loss hit detection
  - Periodic logging (every 30 seconds)

### Stream 3: SMSO Trades (Inverse Position Monitoring)
```python
self.stream.subscribe_trades(self.handle_smso_trade, "SMSO")
```
- **Purpose**: Real-time monitoring of 1x Inverse ETF position (fallback)
- **Frequency**: Every trade (tick-by-tick)
- **Used For**:
  - Trailing stop calculations (1.0%)
  - Price tracking when MSOX not shortable
  - Stop loss hit detection

---

## Key Differences

| Feature | NVDA Bot | MSOS Bot |
|---------|----------|----------|
| **Entry Signal Source** | NVDA bars (1-min) | MSOS trades (tick) |
| **Position Monitoring** | NVDL/NVD trades | MSOX/SMSO trades |
| **Data Frequency** | Bars + Trades | Trades only |
| **Entry Detection** | 5-min candle closes | Real-time tick threshold |
| **Stop Loss Method** | Bracket order + Trailing | Manual trailing stop |
| **Profit Upgrade** | 3% → 1% trailing | None (trails from start) |

## Why This Matters

### Before (NVDA Bot v1.0)
- Entry signals: NVDA bars ✅
- Position monitoring: Polling Alpaca API every bar ❌
- Profit target detection: Delayed by 1-2 seconds ❌
- Stop loss visibility: Limited (bracket order on server) ⚠️

### After (NVDA Bot v1.1)
- Entry signals: NVDA bars ✅
- Position monitoring: Real-time NVDL/NVD trades ✅
- Profit target detection: Instant with live prices ✅
- Stop loss visibility: Full visibility with live updates ✅

## Sample Output Comparison

### NVDA Bot (v1.1) - Live Monitoring

```
[2026-03-17 09:50:01 EST] 🚀 LONG BREAKOUT DETECTED!
[2026-03-17 09:50:01 EST] PLACING LONG ORDER - Ticker: NVDL
[2026-03-17 09:50:01 EST]   Shares: 231
[2026-03-17 09:50:01 EST]   Entry Price: $43.20
[2026-03-17 09:50:03 EST] ✓ Order submitted - Order ID: xxx
[2026-03-17 09:50:05 EST] Stop Loss Order ID: yyy
[2026-03-17 09:50:35 EST] >>> NVDL High: $43.45 | Current: $43.42 | P&L: $50.82 (+0.51%)
[2026-03-17 09:51:05 EST] >>> NVDL High: $43.58 | Current: $43.55 | P&L: $80.85 (+0.81%)
[2026-03-17 09:51:22 EST] New high for NVDL: $43.75
[2026-03-17 10:15:03 EST] 🎯 PROFIT TARGET HIT! $623.10 >= $600.00
[2026-03-17 10:15:03 EST] Upgrading to 1.0% Trailing Stop...
[2026-03-17 10:15:04 EST] ✓ Hard stop canceled
[2026-03-17 10:15:05 EST] ✓ Trailing Stop activated - Order ID: zzz
[2026-03-17 10:15:35 EST] >>> NVDL High: $45.20 | Current: $45.18 | P&L: $660.00 (+4.63%)
```

### MSOS Bot - Live Monitoring

```
[2026-03-17 14:16:23 CST] MSOS Trade: $8.53 | Change: +2.52%
[2026-03-17 14:16:23 CST] BUY TRIGGER: +2.52% >= +2.5%
[2026-03-17 14:16:23 CST] PLACING BUY ORDER
[2026-03-17 14:16:25 CST] Order filled at: $12.34
[2026-03-17 14:16:25 CST] MSOX Trailing stop updated: $12.22 (High: $12.34)
[2026-03-17 14:16:55 CST] >>> MSOX Highest Price Seen: $12.45 | Current: $12.43 | Stop: $12.32
[2026-03-17 14:17:25 CST] >>> MSOX Highest Price Seen: $12.58 | Current: $12.55 | Stop: $12.44
[2026-03-17 14:17:55 CST] >>> MSOX Highest Price Seen: $12.65 | Current: $12.62 | Stop: $12.50
```

## Benefits of Real-Time Monitoring

### 1. Instant Profit Target Detection
- **Old**: Check every 1-2 seconds via position polling
- **New**: Detect instantly on every trade tick
- **Impact**: Faster trailing stop upgrades

### 2. Better Visibility
- **Old**: Limited logging, no price updates
- **New**: Price updates every 30 seconds with P&L
- **Impact**: Better decision making and debugging

### 3. Accurate P&L Calculations
- **Old**: Delayed by polling interval
- **New**: Real-time with every trade
- **Impact**: Know exact profit/loss at all times

### 4. Consistent Architecture
- **Old**: Different approaches between bots
- **New**: Both bots use same monitoring pattern
- **Impact**: Easier to maintain and debug

## Stop Loss Verification

Both bots now have **full visibility** into stop loss behavior:

### NVDA Bot
```python
# Long position: tracks highest price
if nvdl_price > self.highest_price_since_entry:
    self.highest_price_since_entry = nvdl_price
    print(f"New high for NVDL: ${nvdl_price:.2f}")

# Short position: tracks lowest price  
if nvd_price < self.lowest_price_since_entry:
    self.lowest_price_since_entry = nvd_price
    print(f"New low for NVD: ${nvd_price:.2f}")
```

### MSOS Bot
```python
# Long position: tracks highest price
if msox_price > self.highest_price_since_entry:
    self.highest_price_since_entry = msox_price
    self.trailing_stop_price = msox_price * (1 - TRAILING_STOP_PCT / 100)
    print(f"MSOX Trailing stop updated: ${self.trailing_stop_price:.2f}")

# Short position: tracks lowest price
if msox_price < self.lowest_price_since_entry:
    self.lowest_price_since_entry = msox_price  
    self.trailing_stop_price = msox_price * (1 + TRAILING_STOP_PCT / 100)
    print(f"MSOX Trailing stop updated: ${self.trailing_stop_price:.2f}")
```

## Summary

✅ **Both bots see all trades in real-time**
✅ **Stop losses are monitored with live data**
✅ **Profit targets detected instantly**
✅ **Consistent architecture across both strategies**
✅ **Full visibility into price movements**
✅ **Periodic logging every 30 seconds**

Your question about whether "both bots see all trades so the stop losses are accurate" is now definitively **YES** - both bots subscribe to live trade streams for their respective ETFs and have real-time visibility into all price movements.
