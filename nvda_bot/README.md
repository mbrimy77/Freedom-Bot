# NVDA Opening Range Breakout (ORB) Bot

## Strategy Overview

This bot implements a 15-minute Opening Range Breakout strategy on NVDA with three-stage exit logic.

### Signal Generation

- **Monitor Ticker**: NVDA (the underlying stock)
- **15-Min Opening Range**: 9:30 AM – 9:45 AM ET
- **Long Entry**: Buy NVDL (2x Long) if an NVDA 5-minute candle closes ABOVE the 15-min high
- **Short Entry**: Buy NVD (2x Short) if an NVDA 5-minute candle closes BELOW the 15-min low
- **Constraint**: Maximum of one trade per day

### Position Sizing

For a $20,000 account:
- Fixed position size: $20,000
- Shares calculated as: $20,000 / ETF entry price
- Formula accounts for 2x leverage of NVDL/NVD ETFs

### Exit Logic (Three-Stage Risk Management)

**Stage 1 (Hard Stop Loss)**: Immediately place a stop loss at 1.5% below entry price

**Stage 2 (Trailing Stop Upgrade)**: When profit reaches 3% ($600), cancel the hard stop and replace it with a 1.0% trailing stop loss to let winners run

**Stage 3 (End of Day Exit)**: At 2:30 PM CST (3:30 PM ET), the bot closes all positions and cancels all pending orders

> The 2:30 PM CST exit provides a 30-minute buffer before market close at 4:00 PM ET, avoiding end-of-day volatility and ensuring no overnight positions.

## Setup Instructions

### 1. Environment Variables

Create a `.env` file in the `nvda_bot/` directory:

```bash
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
```

### 2. Install Dependencies

```bash
cd nvda_bot
pip install -r requirements.txt
```

### 3. Run the Bot

```bash
python nvda_strategy.py
```

## Railway Deployment

### GitHub Structure

```
your-repo/
├── nvda_bot/
│   ├── nvda_strategy.py
│   ├── requirements.txt
│   ├── railway.toml
│   └── README.md
└── README.md
```

### Railway Configuration

**NVDA Bot Service:**
- **Name**: nvda-bot
- **Root Directory**: `/nvda_bot`
- **Start Command**: `python nvda_strategy.py`
- **Environment Variables**: Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`
- **Replicas**: 1 (CRITICAL - must be exactly 1)
- **Restart Policy**: ON_FAILURE

## End of Day Exit (2:30 PM CST / 3:30 PM ET)

The bot exits all positions at 2:30 PM CST (3:30 PM ET), which provides:

1. **30-minute buffer before market close** - Avoids the volatile 3:30-4:00 PM period
2. **Clean daily reset** - No overnight positions or gap risk
3. **Time discipline** - Forces the strategy to work within a defined 6-hour window (9:30 AM - 3:30 PM ET)

## Time Zones

- **Opening Range**: 9:30 AM - 9:45 AM ET (Eastern Time)
- **Trading Window**: 9:45 AM - 3:30 PM ET (6 hours)
- **End of Day Exit**: 2:30 PM CST / 3:30 PM ET (sharp cutoff)

## Real-Time Monitoring

The bot subscribes to three data streams:

1. **NVDA 1-minute bars** - For tracking opening range and detecting 5-minute breakouts
2. **NVDL live trades** - Real-time monitoring of long positions
3. **NVD live trades** - Real-time monitoring of short positions

This provides:
- Instant profit target detection (no polling delay)
- Real-time P&L updates every 30 seconds
- Accurate price tracking for trailing stop decisions
- Sub-second response time for stop upgrades

## Logging

The bot logs:
- Opening range establishment (9:45 AM ET)
- Entry signals and trade execution
- Position sizing calculations
- Stop loss and trailing stop updates
- Profit target milestones (3% upgrade threshold)
- Real-time price updates (every 30 seconds)
- Current P&L and percentage moves
- End of day exit timestamp (2:30 PM CST / 3:30 PM ET)

## Risk Management

- **Position Size**: $20,000 fixed (accounts for 2x ETF leverage)
- **Hard Stop Loss**: 1.5% from entry price
- **Profit Target**: 3% ($600 on $20k) triggers trailing stop upgrade
- **Trailing Stop**: 1.0% after profit target hit
- **Max Trades**: 1 per day
- **End of Day Exit**: 2:30 PM CST / 3:30 PM ET (mandatory, no exceptions)

## Notes

- The bot uses paper trading by default (set in `TradingClient(paper=True)`)
- Change to live trading by setting `paper=False` when ready
- Always test thoroughly in paper trading before going live
- Monitor Railway logs daily to verify clean exits at 2:30 PM CST
- Ensure Railway replicas = 1 to avoid connection limit errors
