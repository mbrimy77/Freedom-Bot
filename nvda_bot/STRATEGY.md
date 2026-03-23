# NVDA Opening Range Breakout (ORB) Strategy

## Overview

The NVDA ORB strategy is a systematic approach to trading NVDA's volatility during the opening session, with disciplined risk management and a mandatory exit before the afternoon trading session.

## Core Concept

**Opening Range Theory**: The first 15 minutes of trading (9:30-9:45 AM ET) often defines key support and resistance levels for the day. A strong move outside this range suggests directional momentum that can be exploited with leveraged ETFs.

## Strategy Components

### 1. Opening Range Establishment (9:30-9:45 AM ET)

- Monitor NVDA 1-minute bars from 9:30 AM to 9:45 AM Eastern Time
- Record the highest high and lowest low during this 15-minute period
- This establishes our "Opening Range" (ORB)

**Example:**
```
9:30-9:45 AM ET NVDA bars:
High: $875.50
Low: $871.20
ORB Range: $4.30
```

### 2. Breakout Detection (9:45 AM - 3:30 PM ET)

After the ORB is established, we monitor NVDA 5-minute candles for breakouts:

**Long Breakout:**
- A 5-minute candle CLOSES above the ORB high
- Signal: Buy NVDL (2x Long ETF)

**Short Breakout:**
- A 5-minute candle CLOSES below the ORB low
- Signal: Buy NVD (2x Short ETF)

**Key Rules:**
- We only look at CLOSES, not intraday wicks
- Only the first breakout is taken (max 1 trade per day)
- If price whipsaws back and forth, we ignore re-entries

**Example:**
```
9:50 AM: NVDA 5-min candle closes at $876.10
$876.10 > $875.50 (ORB high)
→ LONG BREAKOUT → Buy NVDL
```

### 3. Position Sizing

We size positions to risk exactly $300 on a 1.5% adverse move, accounting for 2x leverage.

**Formula:**
```
Shares = $300 / (Entry Price × 1.5% × 2)
```

**Example:**
```
Entry Price: $43.20
1.5% move: $0.648 per share
For 2x ETF: $0.648 × 2 = $1.296 actual ETF move
Shares = $300 / $1.296 = 231.5 → 231 shares

Position Value: 231 × $43.20 = $9,979.20
If ETF drops 1.5%: $0.648 × 2 × 231 = $299.38 loss ✓
```

**Why This Matters:**
- Consistent risk across all trades regardless of entry price
- Prevents over-sizing when entry price is low
- Prevents under-sizing when entry price is high
- Accounts for 2x leverage of NVDL/NVD

### 4. Exit Logic (The Dual-Stage System)

#### Stage 1: Hard Stop Loss (Immediate)

Upon entry, we immediately place a bracket order with a 1.5% stop loss.

**For Long Positions (NVDL):**
```
Entry: $43.20
Stop: $43.20 × (1 - 1.5%) = $42.55
```

**For Short Positions (NVD):**
```
Entry: $20.50
Stop: $20.50 × (1 + 1.5%) = $20.81
```

This protects us from catastrophic loss if the breakout immediately fails.

#### Stage 2: Trailing Stop Upgrade (If Profit Target Hit)

If the position reaches 3% profit ($600 on $20k account), we upgrade to a more aggressive trailing stop.

**Profit Target Calculation:**
```
Account Size: $20,000
3% Profit: $600
```

**When hit:**
1. Cancel the 1.5% hard stop
2. Place a 1.0% trailing stop order
3. Let the position run with the trailing stop

**Trailing Stop Behavior:**
- For longs: Stop trails 1% below the highest price since upgrade
- For shorts: Stop trails 1% above the lowest price since upgrade
- Allows more room for profit while still protecting gains

**Example:**
```
Entry: $43.20
Position moves to $44.50 (+3.01% = $600.60 profit)
→ Upgrade to 1% trailing stop
→ Initial trail stop: $44.06 (1% below $44.50)

Price moves to $45.00
→ Trail stop updates: $44.55 (1% below $45.00)

Price drops to $44.60
→ Trail stop still at $44.55
→ Position closed at $44.55 for profit
```

#### Stage 3: End of Day Exit (2:30 PM CST / 3:30 PM ET - MANDATORY)

At exactly 2:30 PM Central Time (3:30 PM Eastern Time), all positions are closed regardless of profit or loss.

**Why 2:30 PM CST / 3:30 PM ET?**
- Creates 30-minute buffer before market close at 4:00 PM ET
- Avoids end-of-day volatility and unpredictable closing auction
- Ensures clean daily reset with no overnight positions
- Eliminates gap risk and after-hours exposure

**Exit Process:**
1. Close all positions at market
2. Cancel all pending orders (stops, trails)
3. Log exact exit time and P&L
4. Bot shuts down until next trading day

### 5. Edge Cases and Risk Management

**What if ORB is very narrow?**
- Still take the trade - narrow ranges often lead to explosive moves
- Position sizing automatically adjusts for volatility
- Stop loss protects against false breakouts

**What if breakout happens right at 2:25 PM CST (3:25 PM ET)?**
- No entry - End of day exit takes priority
- Last safe entry should be before 2:00 PM CST to allow proper management

**What if both long and short triggers hit?**
- Only first trigger is taken (first breakout above or below)
- Max 1 trade per day prevents whipsaw losses

**What if stop is hit, then another breakout occurs?**
- No re-entry - max 1 trade per day
- Prevents revenge trading and overtrading

**What if position is at 2.9% profit at 2:30 PM CST?**
- Close it anyway - End of day exit is non-negotiable
- Better to take $580 profit than risk holding through volatile closing period
- System discipline > individual trade optimization

## Psychological Advantages

1. **No Discretion**: Rules are mechanical, reduces emotional decisions
2. **Defined Risk**: Maximum loss is known before entry (1.5% stop)
3. **Time-Bound**: Strategy ends at 2:30 PM CST / 3:30 PM ET, no overnight stress
4. **Profit Protection**: Trailing stop locks in gains after 3% profit
5. **No FOMO**: Max 1 trade per day prevents chasing and overtrading

## Backtesting Considerations

When backtesting this strategy:

- Use actual 5-minute close prices, not intraday highs/lows
- Account for slippage on market orders (typically 2-3 cents)
- Factor in stop loss slippage (market orders on stop hit)
- NVDL/NVD may have wider spreads than NVDA (check bid/ask)
- Consider days where ORB is never broken (flat days)
- Test across different volatility regimes (VIX levels)

## Optimal Market Conditions

**Best:**
- High implied volatility (VIX > 20)
- NVDA earnings week or major news
- Tech sector momentum
- Clear opening gap (up or down)

**Worst:**
- Low volatility, tight ranges
- Choppy, directionless markets
- Major economic data releases at 9:30 AM causing gaps
- NVDA consolidating after large move

## Performance Expectations

**Win Rate:** 40-50% (typical for breakout strategies)

**Risk/Reward:** 
- Average loss: ~$250 (within $300 risk limit)
- Average win: ~$450-600 (when trailing stop works)
- Expectancy: Positive if R:R > 1.5:1

**Max Drawdown:** 
- 5 consecutive losses = $1,500 (7.5% of account)
- Suggests taking a break or adjusting parameters

## Strategy Variations (For Testing)

1. **Tighter ORB**: Use 10-min ORB (9:30-9:40) for earlier entries
2. **Looser Confirmation**: Wait for 15-min candle close (more reliable)
3. **Volume Filter**: Only take breakouts with high volume
4. **Volatility Filter**: Skip days when VIX < 15
5. **Time Filter**: Only trade first breakout before 11:00 AM

## Daily Trading Window

The bot operates within a strict 6-hour window:

**Daily Schedule:**
```
9:30 AM ET: Market opens - Begin tracking opening range
9:45 AM ET: ORB established - Monitor for breakout signals
9:45 AM - 3:30 PM ET: Active trading window (6 hours)
2:30 PM CST / 3:30 PM ET: Mandatory exit - Close all positions
3:30 PM - 9:30 AM ET: Bot idle - No positions held overnight
```

**Benefits of the 3:30 PM ET Exit:**
- Captures morning volatility (most profitable period)
- Avoids unpredictable 3:30-4:00 PM closing volatility
- No overnight gap risk or after-hours exposure
- Clean daily P&L with clear start/end times

## Risk of Ruin

With $300 max loss per trade and $20k account:

- Each trade risks 1.5% of capital
- 10 consecutive losses = 15% drawdown
- Probability of 10 losses in a row at 50% win rate: 0.1%

**Safety Margin**: Very low risk of blowing up account with this position sizing.

## Summary

The NVDA ORB strategy combines:
- **Systematic entry**: Clear rules based on opening range breakouts, no discretion
- **Defined risk**: 1.5% stop loss on every trade
- **Profit optimization**: Trailing stop upgrade after 3% profit target
- **Capital protection**: No overnight positions, exits 30 minutes before market close
- **Time discipline**: Strategy ends at 2:30 PM CST / 3:30 PM ET sharp

This is a mechanical, rule-based strategy that captures NVDA's opening volatility while maintaining strict risk controls and time discipline. The 6-hour trading window focuses on the most volatile and profitable period of the day.
