# Dual-Strategy Automated Trading System

A comprehensive trading system featuring two independent bots running on separate schedules:

1. **NVDA Bot** (9:30 AM - 2:00 PM CST): Opening Range Breakout strategy on NVDA/NVDL/NVD
2. **MSOS Bot** (2:15 PM - 2:58 PM CST): Momentum strategy on MSOS/MSOX

The 15-minute "Golden Gap" (2:00 PM - 2:15 PM) ensures capital is liquid and available for the afternoon MSOS strategy.

## System Architecture

### Bot 1: NVDA Opening Range Breakout (9:30 AM - 2:00 PM CST)

**Strategy**: 15-minute ORB with dual-stage exits

- **Monitor**: NVDA (underlying stock) for 15-min ORB (9:30-9:45 AM ET)
- **Trade**: NVDL (2x Long) or NVD (2x Short) based on 5-min candle closes
- **Position Sizing**: 1.5% move = $300 loss on $20k account
- **Exit Logic**:
  - Stage 1: 1.5% hard stop loss
  - Stage 2: If profit hits 3% ($600), upgrade to 1% trailing stop
  - Stage 3: **GOLDEN GAP EXIT at 2:00 PM CST** (mandatory)
- **Max Trades**: 1 per day

### Bot 2: MSOS Momentum Strategy (2:15 PM - 2:58 PM CST)

**Strategy**: Bi-directional momentum with trailing stops

- **Monitor**: MSOS for momentum signals (+/- 2.5% from previous close)
- **Trade**: MSOX (or SMSO inverse) with $20k notional orders
- **Exit Logic**:
  - 1.0% trailing stop based on MSOX price movements
  - Hard close at 2:58 PM CST for overnight cash position
- **Max Trades**: 1 per day

### The "Golden Gap" (2:00 PM - 2:15 PM CST)

NVDA bot exits at 2:00 PM CST, and MSOS bot starts at 2:01 PM CST but doesn't enter trades until 2:15 PM. This ensures:

1. NVDA positions are fully closed and settled
2. Alpaca websocket connection is freed (no connection limit issues)
3. Buying power is updated in Alpaca account
4. Full $20,000 capital is available for MSOS bot
5. No collision between strategies

## Repository Structure

```
├── nvda_bot/
│   ├── nvda_strategy.py       # NVDA ORB bot
│   ├── requirements.txt
│   ├── README.md
│   ├── DEPLOYMENT.md          # Railway deployment guide
│   ├── .env.example
│   └── .gitignore
├── msos_bot/
│   ├── momentum_bot.py        # MSOS momentum bot
│   └── requirements.txt
├── momentum_bot.py            # (legacy, move to msos_bot/)
└── README.md                  # This file
```

## Setup

### Option 1: Run Locally (for testing)

**NVDA Bot:**
```bash
cd nvda_bot
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Alpaca API keys
python nvda_strategy.py
```

**MSOS Bot:**
```bash
cd msos_bot
pip install -r requirements.txt
# Use same .env as above or create new one
python momentum_bot.py
```

### Option 2: Deploy to Railway (for production)

See `nvda_bot/DEPLOYMENT.md` for comprehensive Railway deployment instructions.

**Quick Setup:**
1. Push both `nvda_bot/` and `msos_bot/` to GitHub
2. Create Railway project
3. Add two services:
   - Service 1: Root Directory = `/nvda_bot`, Start Command = `python nvda_strategy.py`
   - Service 2: Root Directory = `/msos_bot`, Start Command = `python momentum_bot.py`
4. Set environment variables (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`) for each service
5. Deploy and monitor logs

## Configuration

### NVDA Bot (`nvda_bot/nvda_strategy.py`)

```python
MONITOR_TICKER = "NVDA"          # Monitor for ORB signals
LONG_TICKER = "NVDL"             # 2x Long ETF
SHORT_TICKER = "NVD"             # 2x Short ETF
ACCOUNT_SIZE = 20000             # $20k account
RISK_AMOUNT = 300                # $300 max loss per trade
HARD_STOP_PCT = 1.5              # 1.5% hard stop
PROFIT_TARGET_PCT = 3.0          # 3% profit target
TRAILING_STOP_PCT = 1.0          # 1% trailing stop
ORB_START = time(9, 30)          # 9:30 AM ET
ORB_END = time(9, 45)            # 9:45 AM ET
GOLDEN_GAP_EXIT = time(14, 0)    # 2:00 PM CST
```

### MSOS Bot (`msos_bot/momentum_bot.py`)

```python
MONITOR_TICKER = "MSOS"          # Monitor for signals
TRADE_TICKER = "MSOX"            # Execute trades
INVERSE_TICKER = "SMSO"          # Inverse ticker fallback
NOTIONAL_AMOUNT = 20000          # $20k per trade
TRIGGER_THRESHOLD = 2.5          # +/- 2.5% trigger
TRAILING_STOP_PCT = 1.0          # 1.0% trailing stop
TRIGGER_START = time(14, 15)     # 2:15 PM CT
TRIGGER_END = time(14, 30)       # 2:30 PM CT
EXIT_TIME = time(14, 58)         # 2:58 PM CT
```

## How It Works

### Daily Schedule

**9:30 AM ET** - NVDA bot starts, establishes 15-min opening range

**9:45 AM ET** - NVDA bot begins monitoring for 5-min breakouts

**2:00 PM CST** - **GOLDEN GAP**: NVDA bot closes all positions and stops

**2:01 PM CST** - MSOS bot starts up and connects to Alpaca

**2:15 PM CST** - MSOS bot begins monitoring for momentum signals (entry window opens)

**2:30 PM CST** - MSOS bot entry window closes

**2:58 PM CST** - MSOS bot closes all positions and stops

### NVDA Bot Workflow

1. **Establish ORB** (9:30-9:45 AM ET):
   - Tracks NVDA 1-minute bars
   - Calculates 15-min high/low range
   
2. **Monitor Breakouts** (9:45 AM - 2:00 PM CST):
   - Watches NVDA 5-minute candles
   - Long entry: 5-min close > ORB high → Buy NVDL (2x)
   - Short entry: 5-min close < ORB low → Buy NVD (2x)
   - Calculates position size for $300 max loss (1.5% stop)
   
3. **Dual-Stage Exit**:
   - Stage 1: 1.5% hard stop loss placed immediately
   - Stage 2: If profit hits 3%, upgrade to 1% trailing stop
   - Stage 3: Hard exit at 2:00 PM CST (Golden Gap)

### MSOS Bot Workflow

1. **Startup**:
   - Fetches previous day's closing price for MSOS
   - Calculates trigger levels (+2.5% and -2.5%)
   - Subscribes to MSOS and MSOX live trade streams

2. **Monitoring Phase** (2:15-2:30 PM CST):
   - Watches every MSOS trade tick
   - If MSOS ≥ +2.5%: Places $20k buy order for MSOX
   - If MSOS ≤ -2.5%: Places $20k short order for MSOX (or buy SMSO)
   - Only enters once per day

3. **Position Management**:
   - **Long positions**: Tracks highest price, updates stop 1.0% below
   - **Short positions**: Tracks lowest price, updates stop 1.0% above
   - Logs status every 30 seconds

4. **Exit**:
   - Automatically closes all positions at 2:58 PM CST
   - Ensures overnight cash position

## Strategy Comparison

| Feature | NVDA Bot | MSOS Bot |
|---------|----------|----------|
| **Underlying** | NVDA (stock) | MSOS (ETF) |
| **Trade Tickers** | NVDL (2x Long), NVD (2x Short) | MSOX (3x Long/Short), SMSO (1x Inverse) |
| **Strategy Type** | Opening Range Breakout | Momentum Breakout |
| **Entry Signal** | 5-min candle close outside 15-min ORB | +/- 2.5% from previous close |
| **Time Window** | 9:30 AM ET - 2:00 PM CST | 2:15 PM CST - 2:58 PM CST |
| **Position Sizing** | Calculated for $300 max loss | $20k notional |
| **Initial Stop** | 1.5% hard stop | 1.0% trailing stop |
| **Profit Target** | 3% ($600) → upgrade to 1% trailing | None (trailing from entry) |
| **Max Trades/Day** | 1 | 1 |
| **Exit Time** | 2:00 PM CST (Golden Gap) | 2:58 PM CST (overnight cash) |

## Sample Output

### NVDA Bot

```
[2026-03-17 09:30:00 EST] NVDA ORB Bot initialized
[2026-03-17 09:45:01 EST] ✓ Opening Range Established (9:30-9:45 AM ET)
[2026-03-17 09:45:01 EST] ORB High: $875.50
[2026-03-17 09:45:01 EST] ORB Low: $871.20
[2026-03-17 09:50:00 EST] 🚀 LONG BREAKOUT DETECTED!
[2026-03-17 09:50:00 EST] 5-min Close: $876.10 > ORB High: $875.50
[2026-03-17 09:50:01 EST] PLACING LONG ORDER
[2026-03-17 09:50:01 EST]   Ticker: NVDL
[2026-03-17 09:50:01 EST]   Shares: 456
[2026-03-17 09:50:01 EST]   Entry Price: $43.20
[2026-03-17 09:50:01 EST]   Stop Loss: $42.55 (1.5%)
[2026-03-17 10:15:23 EST] 🎯 PROFIT TARGET HIT! $615.00 >= $600.00
[2026-03-17 10:15:23 EST] Upgrading to 1.0% Trailing Stop...
[2026-03-17 14:00:00 CST] CLOSING ALL POSITIONS - GOLDEN GAP EXIT
[2026-03-17 14:00:00 CST] ✓ Closed position: NVDL
[2026-03-17 14:00:01 CST] Golden Gap exit time reached. Bot stopping.
```

### MSOS Bot

```
[2026-03-17 14:15:00 CST] MOMENTUM TRADING BOT STARTED
[2026-03-17 14:15:00 CST] Previous close for MSOS: $8.32
[2026-03-17 14:16:23 CST] MSOS Trade: $8.53 | Change: +2.52%
[2026-03-17 14:16:23 CST] BUY TRIGGER: +2.52% >= +2.5%
[2026-03-17 14:16:23 CST] PLACING BUY ORDER
[2026-03-17 14:16:25 CST] Order filled at: $12.34
[2026-03-17 14:16:25 CST] MSOX Trailing stop updated: $12.22 (High: $12.34)
[2026-03-17 14:16:55 CST] >>> MSOX Highest Price Seen: $12.45 | Current: $12.43 | Stop: $12.32
[2026-03-17 14:58:00 CST] CLOSING ALL POSITIONS (Hard Exit)
```

## Safety Features

### Risk Management

- **Capital Isolation**: Each bot uses the same $20k account but runs at different times
- **Position Sizing**: NVDA bot calculates exact shares for $300 max loss
- **Max Trades**: Both bots limited to 1 trade per day
- **Hard Stops**: Immediate stop losses on all entries
- **No Overnight Risk**: Both bots close all positions before market close

### Technical Safeguards

- Paper trading enabled by default (`paper=True`)
- Single entry rule prevents duplicate positions
- Position existence check before entry
- Golden Gap ensures capital liquidity between strategies
- Comprehensive error handling and logging
- Real-time P&L monitoring for profit target upgrades

### Time Zone Management

- NVDA bot uses Eastern Time (ET) for ORB and Central Time (CST) for exit
- MSOS bot uses Central Time (CST) throughout
- All timestamps logged with timezone for clarity

## Performance Tracking

Both bots log:
- Entry/exit prices and times
- Position sizing calculations
- Stop loss levels and updates
- Profit/loss at exit
- Golden Gap exit confirmations

Review Alpaca dashboard daily to track:
- Total P&L by strategy
- Win rate and average win/loss
- Slippage on entries/exits
- Capital utilization efficiency

## Troubleshooting

**NVDA bot doesn't establish ORB:**
- Check market is open 9:30-9:45 AM ET
- Verify NVDA has sufficient trading volume
- Review bar data availability in logs

**MSOS bot doesn't have capital at 2:15 PM:**
- Verify NVDA bot closed at 2:00 PM CST (check logs)
- Check Alpaca account settlement status
- Consider increasing Golden Gap buffer to 20 minutes

**Position sizing incorrect:**
- Verify `ACCOUNT_SIZE` matches actual buying power
- Check `RISK_AMOUNT` is set to desired max loss
- Review position sizing logs for calculation details

**Trailing stop not upgrading:**
- Confirm profit target hit (check P&L logs)
- Verify stop loss order cancellation
- Check Alpaca orders dashboard for trailing stop creation

## Next Steps

1. **Test in Paper Trading**: Run both bots for 1-2 weeks
2. **Monitor Golden Gap**: Verify 2:00 PM exits happen consistently
3. **Review Performance**: Analyze win rate, average P&L, max drawdown
4. **Optimize Parameters**: Adjust stops, profit targets, or ORB period if needed
5. **Go Live**: Switch `paper=False` when ready

## Resources

- **NVDA Bot README**: See `nvda_bot/README.md` for detailed strategy docs
- **Deployment Guide**: See `nvda_bot/DEPLOYMENT.md` for Railway setup
- **Alpaca Docs**: https://alpaca.markets/docs/python-sdk/
- **alpaca-py GitHub**: https://github.com/alpacahq/alpaca-py
