# NVDA Opening Range Breakout (ORB) Bot

## Strategy Overview

This bot implements a 15-minute Opening Range Breakout strategy on NVDA with dual-stage exit logic.

### Signal Generation

- **Monitor Ticker**: NVDA (the underlying stock)
- **15-Min Opening Range**: 9:30 AM – 9:45 AM ET
- **Long Entry**: Buy NVDL (2x Long) if an NVDA 5-minute candle closes ABOVE the 15-min high
- **Short Entry**: Buy NVD (2x Short) if an NVDA 5-minute candle closes BELOW the 15-min low
- **Constraint**: Maximum of one trade per day

### Position Sizing

For a $20,000 account:
- Calculate shares so that a 1.5% move against entry equals exactly $300 loss
- Formula accounts for 2x leverage of NVDL/NVD ETFs

### Exit Logic (The "Golden Gap" Rule)

**Stage 1 (Hard Stop)**: Immediately place a static stop loss at 1.5% below entry

**Stage 2 (The Chaser)**: If profit hits 3% ($600), cancel the hard stop and replace it with a 1.0% trailing stop loss

**Stage 3 (THE ABSOLUTE CUTOFF)**: At exactly 2:00 PM CST, the bot cancels all pending orders and closes all positions

> The 2:00 PM exit creates a 15-minute buffer before the MSOS bot wakes up at 2:15 PM, ensuring the $20,000 is liquid and available.

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
├── msos_bot/
│   ├── momentum_bot.py
│   └── requirements.txt
├── nvda_bot/
│   ├── nvda_strategy.py
│   └── requirements.txt
└── README.md
```

### Railway Configuration

Create two separate services:

**Service 1: NVDA Bot**
- **Name**: nvda-bot
- **Root Directory**: `/nvda_bot`
- **Start Command**: `python nvda_strategy.py`
- **Environment Variables**: Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`

**Service 2: MSOS Bot**
- **Name**: msos-bot
- **Root Directory**: `/msos_bot`
- **Start Command**: `python momentum_bot.py`
- **Environment Variables**: Set `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`

## The "Golden Gap" (2:00 PM to 2:15 PM)

By coding the exit at 2:00 PM CST, you give the Alpaca system and Railway 15 minutes to:

1. Settle the trade
2. Update your "Buying Power" balance
3. Ensure the MSOS bot sees the full $20,000 available when it wakes up at 2:15 PM

This prevents any collision between the two strategies and ensures both have full capital access.

## Time Zones

- **Opening Range**: 9:30 AM - 9:45 AM ET (Eastern Time)
- **Trading Window**: 9:45 AM ET - 2:00 PM CST (Central Time)
- **Golden Gap Exit**: 2:00 PM CST (sharp cutoff)
- **MSOS Bot Start**: 2:15 PM CST

## Real-Time Monitoring

The bot subscribes to three data streams:

1. **NVDA 1-minute bars** - For detecting 5-minute breakouts
2. **NVDL live trades** - Real-time monitoring of long positions
3. **NVD live trades** - Real-time monitoring of short positions

This provides:
- Instant profit target detection (no polling delay)
- Real-time P&L updates every 30 seconds
- Accurate price tracking for trailing stop decisions
- Consistent architecture with MSOS bot

## Logging

The bot logs:
- Opening range establishment
- Entry signals and trade execution
- Position sizing calculations
- Stop loss and trailing stop updates
- Profit target milestones
- Real-time price updates (every 30 seconds)
- Current P&L and percentage moves
- Golden Gap exit timestamp (for verification)

## Risk Management

- **Maximum Risk Per Trade**: $300 (1.5% of $20k account)
- **Hard Stop Loss**: 1.5% from entry
- **Profit Target**: 3% ($600) triggers trailing stop upgrade
- **Trailing Stop**: 1.0% after profit target hit
- **Max Trades**: 1 per day
- **Hard Exit**: 2:00 PM CST (no exceptions)

## Notes

- The bot uses paper trading by default (set in `TradingClient(paper=True)`)
- Change to live trading by setting `paper=False` when ready
- Always test thoroughly in paper trading before going live
- Monitor the 2:00 PM exit logs to ensure the Golden Gap is working correctly
