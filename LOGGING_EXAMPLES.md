# Complete Logging Examples - What You'll See

## 📊 **NVDA Bot - Complete Trade Lifecycle**

### **1. Entry Signal & Order Placement**

```
[2026-03-19 10:15:00 EDT] LONG BREAKOUT DETECTED!
[2026-03-19 10:15:00 EDT] 5-min Close: $876.10 > ORB High: $875.50

[2026-03-19 10:15:01 EDT] PLACING LONG ORDER
[2026-03-19 10:15:01 EDT] Ticker: NVDL
[2026-03-19 10:15:01 EDT] Shares: 231
[2026-03-19 10:15:01 EDT] Entry Price: $43.20
[2026-03-19 10:15:01 EDT] Expected Max Loss: $299.65
[2026-03-19 10:15:01 EDT] Stop Loss: $42.55 (1.5%)
[2026-03-19 10:15:02 EDT] Order submitted - Order ID: abc123xyz
[2026-03-19 10:15:03 EDT] Stop Loss Order ID: def456uvw
```

### **2. Real-Time Position Monitoring (Every 30 seconds)**

```
[2026-03-19 10:15:35 EDT] >>> NVDL High: $43.45 | Current: $43.42 | P&L: $50.82 (+0.51%)
[2026-03-19 10:16:05 EDT] >>> NVDL High: $43.58 | Current: $43.55 | P&L: $80.85 (+0.81%)
[2026-03-19 10:16:35 EDT] New high for NVDL: $43.75
[2026-03-19 10:17:05 EDT] >>> NVDL High: $43.75 | Current: $43.70 | P&L: $115.50 (+1.16%)
[2026-03-19 10:17:35 EDT] >>> NVDL High: $43.85 | Current: $43.80 | P&L: $138.60 (+1.39%)
```

### **3. Profit Target Hit (If Reached)**

```
[2026-03-19 10:25:15 EDT] PROFIT TARGET HIT! $645.00 >= $600.00
[2026-03-19 10:25:15 EDT] Upgrading to 1.0% Trailing Stop...
[2026-03-19 10:25:16 EDT] Hard stop canceled
[2026-03-19 10:25:17 EDT] Trailing Stop activated - Order ID: ghi789rst
```

### **4. Exit & Final Summary**

```
[2026-03-19 14:00:00 CST] CLOSING ALL POSITIONS - GOLDEN GAP EXIT at 2026-03-19 14:00:00 CST

[2026-03-19 14:00:00 CST] === FINAL TRADE SUMMARY ===
[2026-03-19 14:00:00 CST] Symbol: NVDL
[2026-03-19 14:00:00 CST] Entry Price: $43.20
[2026-03-19 14:00:00 CST] Exit Price: $44.50
[2026-03-19 14:00:00 CST] Shares: 231
[2026-03-19 14:00:00 CST] Final P&L: $300.30 (+3.01%)
[2026-03-19 14:00:00 CST] ==========================

[2026-03-19 14:00:01 CST] Position closed successfully
[2026-03-19 14:00:01 CST] All pending orders canceled
[2026-03-19 14:00:01 CST] Golden Gap exit time reached. Bot stopping.
```

---

## 📊 **MSOS Bot - Complete Trade Lifecycle**

### **1. Entry Signal & Order Placement**

```
[2026-03-19 14:16:23 CST] MSOS Trade: $8.53 | Change: +2.52%
[2026-03-19 14:16:23 CST] BUY TRIGGER: +2.52% >= +2.5%

[2026-03-19 14:16:23 CST] PLACING BUY ORDER
[2026-03-19 14:16:23 CST] Ticker: MSOX
[2026-03-19 14:16:23 CST] Notional Amount: $20000
[2026-03-19 14:16:25 CST] Order submitted successfully - Order ID: jkl123mno
```

### **2. Order Fill Confirmation**

```
[2026-03-19 14:16:27 CST] Order filled at: $12.34
[2026-03-19 14:16:27 CST] MSOX Trailing stop updated: $12.22 (High: $12.34)
```

### **3. Real-Time Position Monitoring (Every 30 seconds)**

```
[2026-03-19 14:16:57 CST] >>> MSOX Highest Price Seen: $12.45 | Current: $12.43 | Stop: $12.32
[2026-03-19 14:17:27 CST] >>> MSOX Highest Price Seen: $12.58 | Current: $12.55 | Stop: $12.45
[2026-03-19 14:17:57 CST] >>> MSOX Highest Price Seen: $12.65 | Current: $12.62 | Stop: $12.52
[2026-03-19 14:18:27 CST] >>> MSOX Highest Price Seen: $12.78 | Current: $12.75 | Stop: $12.65
```

### **4. Trailing Stop Updates (When New Highs/Lows Hit)**

```
[2026-03-19 14:19:05 CST] MSOX Trailing stop updated: $12.65 (High: $12.78)
[2026-03-19 14:19:45 CST] MSOX Trailing stop updated: $12.78 (High: $12.91)
```

### **5. Exit & Final Summary**

```
[2026-03-19 14:58:00 CST] CLOSING ALL POSITIONS (Hard Exit)

[2026-03-19 14:58:00 CST] === FINAL TRADE SUMMARY ===
[2026-03-19 14:58:00 CST] Symbol: MSOX
[2026-03-19 14:58:00 CST] Entry Price: $12.34
[2026-03-19 14:58:00 CST] Exit Price: $12.85
[2026-03-19 14:58:00 CST] Shares/Notional: 1620 shares
[2026-03-19 14:58:00 CST] Final P&L: $826.20 (+4.13%)
[2026-03-19 14:58:00 CST] ==========================

[2026-03-19 14:58:01 CST] Position closed successfully
```

---

## 🎯 **What Information You Get:**

### **At Entry:**
✅ Entry signal details (breakout or momentum trigger)  
✅ Ticker being traded  
✅ Number of shares  
✅ Entry price  
✅ Stop loss level  
✅ Order ID for tracking  

### **During Trade (Every 30 seconds):**
✅ Current price  
✅ Highest/lowest price since entry  
✅ Current P&L in dollars  
✅ Current P&L in percentage  
✅ Stop loss level (if trailing)  

### **At Exit:**
✅ **Final Trade Summary Box**  
✅ Entry price  
✅ Exit price  
✅ Total shares  
✅ **Final P&L in dollars**  
✅ **Final P&L in percentage**  

---

## 📱 **How to Monitor in Railway:**

1. **Go to Railway Dashboard**
2. **Click on service** (nvda-bot or msos-bot)
3. **Click "Deployments"** tab
4. **Click latest deployment**
5. **Logs show in real-time**

**Pro Tip:** Keep Railway logs open in a browser tab during trading hours to watch in real-time!

---

## 🔍 **Example Losing Trade (Stop Loss Hit):**

### **NVDA Bot - Stop Loss**

```
[2026-03-19 10:15:00 EDT] LONG BREAKOUT DETECTED!
[2026-03-19 10:15:01 EDT] PLACING LONG ORDER
[2026-03-19 10:15:01 EDT] Entry Price: $43.20
[2026-03-19 10:15:01 EDT] Stop Loss: $42.55 (1.5%)

[2026-03-19 10:15:35 EDT] >>> NVDL High: $43.25 | Current: $43.20 | P&L: $0.00 (+0.00%)
[2026-03-19 10:16:05 EDT] >>> NVDL High: $43.25 | Current: $43.10 | P&L: -$23.10 (-0.23%)
[2026-03-19 10:16:35 EDT] >>> NVDL High: $43.25 | Current: $42.95 | P&L: -$57.75 (-0.58%)
[2026-03-19 10:17:05 EDT] >>> NVDL High: $43.25 | Current: $42.80 | P&L: -$92.40 (-0.93%)

[Alpaca closes position via stop loss order]

[2026-03-19 10:17:15 EDT] CLOSING ALL POSITIONS - Stop loss hit

[2026-03-19 10:17:15 EDT] === FINAL TRADE SUMMARY ===
[2026-03-19 10:17:15 EDT] Symbol: NVDL
[2026-03-19 10:17:15 EDT] Entry Price: $43.20
[2026-03-19 10:17:15 EDT] Exit Price: $42.55
[2026-03-19 10:17:15 EDT] Shares: 231
[2026-03-19 10:17:15 EDT] Final P&L: -$150.15 (-1.50%)
[2026-03-19 10:17:15 EDT] ==========================
```

---

## 💡 **Tips for Reading Logs:**

1. **Look for "PLACING ORDER"** - Entry signal  
2. **Watch ">>>" lines** - Real-time P&L updates  
3. **Look for "FINAL TRADE SUMMARY"** - Complete results  
4. **Check timestamps** - Verify Golden Gap timing  

---

## ✅ **Summary:**

You'll see:
- ✅ **When trades happen** (exact time, price, shares)
- ✅ **Live P&L updates** (every 30 seconds)
- ✅ **Final results** (exact profit/loss when closed)
- ✅ **All important events** (stop loss, profit target, exits)

**Everything you need to track your trading in real-time!** 📊
