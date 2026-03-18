# Quick Start Guide - Dual Strategy Trading System

## Prerequisites

- Python 3.9 or higher
- Alpaca brokerage account (paper or live)
- API keys from Alpaca dashboard

## 5-Minute Setup (Paper Trading)

### 1. Clone/Download Repository

```bash
cd C:\Users\matth
# Your code is already here!
```

### 2. Set Up NVDA Bot

```bash
cd nvda_bot
pip install -r requirements.txt
```

Create `.env` file:
```bash
ALPACA_API_KEY=PKxxxxxxxxxxxxxxxxxx
ALPACA_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Test it:
```bash
python nvda_strategy.py
```

You should see:
```
[TIMESTAMP] NVDA ORB Bot initialized
[TIMESTAMP] Monitor Ticker: NVDA
[TIMESTAMP] Establishing 15-minute Opening Range...
```

### 3. Set Up MSOS Bot

```bash
cd ../msos_bot  # or use existing momentum_bot.py location
pip install -r requirements.txt
# Use same .env as NVDA bot
```

Test it:
```bash
python momentum_bot.py
```

You should see:
```
[TIMESTAMP] Bot initialized
[TIMESTAMP] Monitor Ticker: MSOS
[TIMESTAMP] Fetching previous close for MSOS...
```

### 4. Test Schedule (Paper Trading)

**Morning (9:30 AM ET):**
- Run NVDA bot: `python nvda_bot/nvda_strategy.py`
- Let it run until 2:00 PM CST
- Verify it exits cleanly at 2:00 PM

**Afternoon (2:15 PM CST):**
- Run MSOS bot: `python msos_bot/momentum_bot.py`
- Let it run until 2:58 PM CST
- Verify it exits cleanly at 2:58 PM

**Check Alpaca Dashboard:**
- Review all orders and positions
- Verify capital flow (buying power)
- Check P&L for each bot

## Production Deployment (Railway)

### 1. Organize GitHub Repository

Move `momentum_bot.py` to `msos_bot/` folder:

```bash
mkdir msos_bot
move momentum_bot.py msos_bot/
# Copy requirements.txt to msos_bot/
```

Push to GitHub:
```bash
git add nvda_bot/ msos_bot/
git commit -m "Add dual-strategy trading system"
git push origin main
```

### 2. Deploy to Railway

Go to https://railway.app

**Create New Project** → "Deploy from GitHub repo"

**Add Service 1 (NVDA Bot):**
- Name: `nvda-bot`
- Root Directory: `/nvda_bot`
- Start Command: `python nvda_strategy.py`
- Add environment variables:
  - `ALPACA_API_KEY`
  - `ALPACA_SECRET_KEY`

**Add Service 2 (MSOS Bot):**
- Name: `msos-bot`
- Root Directory: `/msos_bot`
- Start Command: `python momentum_bot.py`
- Add environment variables:
  - `ALPACA_API_KEY`
  - `ALPACA_SECRET_KEY`

### 3. Monitor Logs

In Railway dashboard:
- Click on each service
- View "Logs" tab
- Verify bots start/stop at correct times
- Check for errors

**Key Log Messages to Watch:**

**NVDA Bot:**
```
✓ Opening Range Established
🚀 LONG BREAKOUT DETECTED! or 🔻 SHORT BREAKOUT DETECTED!
CLOSING ALL POSITIONS - GOLDEN GAP EXIT at 14:00:00 CST
```

**MSOS Bot:**
```
BUY TRIGGER: +2.XX% >= +2.5%
Order filled at: $XX.XX
CLOSING ALL POSITIONS (Hard Exit)
```

## Safety Checklist

Before going live:

- [ ] Test both bots in paper trading for at least 5 trading days
- [ ] Verify Golden Gap exit works (2:00 PM CST)
- [ ] Confirm capital is available for MSOS bot at 2:15 PM
- [ ] Review all trades in Alpaca dashboard
- [ ] Check position sizing is correct (NVDA: $300 risk, MSOS: $20k notional)
- [ ] Verify stop losses are placed correctly
- [ ] Test trailing stop upgrade in NVDA bot (reach 3% profit)
- [ ] Confirm no overnight positions remain

## Switching to Live Trading

When ready to go live:

1. **Update bot code:**
   - Change `paper=True` to `paper=False` in both bots
   - Commit and push to GitHub

2. **Railway will auto-redeploy**
   - Monitor first live trade closely
   - Start with 1 week of live trading
   - Scale up gradually

3. **Set up alerts:**
   - Email alerts for errors
   - SMS for trade executions (optional)
   - Slack/Discord webhooks for notifications

## Daily Checklist

**Before Market Open (9:00 AM):**
- [ ] Check both Railway services are running
- [ ] Verify Alpaca API is accessible
- [ ] Confirm $20k buying power available
- [ ] Review any open positions (should be none)

**During Trading (Throughout Day):**
- [ ] Monitor NVDA bot logs (9:30 AM - 2:00 PM CST)
- [ ] Check Golden Gap exit at 2:00 PM
- [ ] Monitor MSOS bot logs (2:15 PM - 2:58 PM CST)
- [ ] Verify all positions closed by 2:58 PM

**After Market Close (4:00 PM ET):**
- [ ] Review trade history in Alpaca
- [ ] Calculate daily P&L
- [ ] Check for any errors in logs
- [ ] Verify account balance is correct

## Troubleshooting

**Bot didn't start:**
- Check Railway service status
- Verify environment variables are set
- Review error logs in Railway dashboard

**Bot didn't exit at scheduled time:**
- Check system time/timezone settings
- Verify hard exit code is not commented out
- Review logs for exceptions

**Capital not available for MSOS bot:**
- Check NVDA bot closed at 2:00 PM (not 2:15 PM)
- Verify trade settlement in Alpaca
- Consider increasing Golden Gap buffer to 20 minutes

**Stop loss didn't trigger:**
- Check order status in Alpaca dashboard
- Verify bracket order was placed correctly
- Review market data for price movements

## Support Resources

- **Alpaca API Docs**: https://alpaca.markets/docs/
- **alpaca-py GitHub**: https://github.com/alpacahq/alpaca-py
- **Railway Docs**: https://docs.railway.app/
- **Strategy Details**: See `nvda_bot/STRATEGY.md` and `README.md`
- **Deployment Guide**: See `nvda_bot/DEPLOYMENT.md`

## Performance Tracking

Use a spreadsheet to track:

| Date | NVDA Bot P&L | MSOS Bot P&L | Total P&L | Notes |
|------|--------------|--------------|-----------|-------|
| 2026-03-17 | +$425 | -$150 | +$275 | NVDA long breakout, MSOS stopped out |
| 2026-03-18 | No trade | +$380 | +$380 | NVDA no breakout, MSOS momentum play |

**Weekly review:**
- Calculate win rate for each strategy
- Review average win/loss
- Identify best/worst performing days
- Adjust parameters if needed (after sufficient data)

## Next Steps

1. Run both bots in paper trading for 1-2 weeks
2. Review performance and logs daily
3. Verify Golden Gap timing is consistent
4. Deploy to Railway and test in production environment
5. Switch to live trading when confident
6. Scale position sizes gradually (if desired)

## Emergency Contacts

**Stop All Trading:**
1. Log into Railway → Pause both services
2. Log into Alpaca → Close all positions manually
3. Review logs to diagnose issue

**Alpaca Support:**
- Email: support@alpaca.markets
- Live chat: Available in Alpaca dashboard

**Railway Support:**
- Discord: https://discord.gg/railway
- Docs: https://docs.railway.app/

---

**Remember**: Start with paper trading, test thoroughly, and only go live when you're confident the bots work as expected. The Golden Gap is critical - verify it works correctly before risking real capital!
