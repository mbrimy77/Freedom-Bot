# Railway Deployment Guide for NVDA Bot

## Prerequisites

1. GitHub repository with your code
2. Railway account (https://railway.app)
3. Alpaca API credentials

## Step-by-Step Deployment

### 1. Prepare GitHub Repository

Your repository should have this structure:

```
your-repo/
├── nvda_bot/
│   ├── nvda_strategy.py
│   ├── requirements.txt
│   ├── railway.toml
│   ├── README.md
│   └── .gitignore
└── README.md
```

Push the folder to GitHub:

```bash
git add nvda_bot/
git commit -m "Add NVDA trading bot"
git push origin main
```

### 2. Create Railway Project

1. Go to Railway dashboard (https://railway.app)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your repository

**Create NVDA Service:**
- Click "Add Service" → "GitHub Repo"
- **Service Name**: `nvda-bot`
- **Settings** → **Root Directory**: `/nvda_bot`
- **Settings** → **Start Command**: `python nvda_strategy.py`
- **Variables** tab:
  - Add `ALPACA_API_KEY`: (your Alpaca API key)
  - Add `ALPACA_SECRET_KEY`: (your Alpaca secret key)

### 3. Configure Environment Variables

In Railway, add these environment variables:

```
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
```

### 4. Deployment Settings

**NVDA Bot Settings:**
- **Runtime**: Python 3.11+
- **Root Directory**: `/nvda_bot`
- **Start Command**: `python nvda_strategy.py`
- **Replicas**: 1 (CRITICAL - must be exactly 1)
- **Restart Policy**: ON_FAILURE
- **Max Retries**: 10
- **Region**: Choose closest to your location (US East or West recommended)

### 5. Verify Deployment

After deployment, check the Railway logs. The bot should show:

**Successful Startup:**
```
[TIMESTAMP] NVDA Bot Starting...
[TIMESTAMP] Connection successful - Account: PA3OVLQ636WP
[TIMESTAMP] Connection lock acquired
[TIMESTAMP] No unexpected positions - ready to trade
[TIMESTAMP] NVDA ORB Bot initialized
[TIMESTAMP] Monitor Ticker: NVDA
[TIMESTAMP] Long Ticker: NVDL (2x)
[TIMESTAMP] Short Ticker: NVD (2x)
[TIMESTAMP] ORB tracking enabled - will track 9:30-9:45 AM range
```

**Opening Range Established (9:45 AM ET):**
```
[TIMESTAMP] ===== OPENING RANGE ESTABLISHED =====
[TIMESTAMP] ORB High: $174.81
[TIMESTAMP] ORB Low: $174.64
[TIMESTAMP] Now monitoring 5-minute candles for breakouts...
```

**End of Day Exit (2:30 PM CST / 3:30 PM ET):**
```
[2026-03-17 14:30:00 CDT] ======================================================================
[2026-03-17 14:30:00 CDT] CLOSING ALL POSITIONS - END OF DAY EXIT at 2026-03-17 14:30:00 CDT
[2026-03-17 14:30:00 CDT] ======================================================================
[2026-03-17 14:30:00 CDT] Symbol: NVDL
[2026-03-17 14:30:00 CDT] Final P&L: $422.54 (+2.11%)
[2026-03-17 14:30:00 CDT] ✅ POSITION CLOSED - VERIFIED WITH ALPACA
```

## Troubleshooting

### Bot Doesn't Start

**Check:**
- Root directory is set correctly (`/nvda_bot`)
- Start command is correct (`python nvda_strategy.py`)
- Environment variables are set (ALPACA_API_KEY and ALPACA_SECRET_KEY)
- `requirements.txt` exists in the root directory
- Railway is using Python 3.11+

### "Module Not Found" Error

Railway should auto-install from `requirements.txt`. If not:
- Check that `railway.toml` exists with proper build configuration
- Verify `requirements.txt` has all dependencies listed
- Check Railway build logs for installation errors

### Connection Limit Exceeded Error

**This is the most common issue. Solutions:**
1. **Verify Railway replicas = 1** (not 2 or more)
2. Check that no other bot/service is using the same Alpaca API keys
3. Restart the Railway service to kill all instances
4. The bot has exponential backoff built-in to handle transient issues

### Position Not Closing at 2:30 PM CST

**Verify:**
- Bot timezone settings (CST = America/Chicago, ET = America/New_York)
- System time on Railway (should be UTC, bot converts internally)
- Check logs for exact exit timestamp
- Ensure `END_OF_DAY_EXIT = time(14, 30)` in code (2:30 PM CST)

## Best Practices

1. **Paper Trading First**: Test the bot in paper mode for at least 1 week
2. **Monitor Logs**: Check Railway logs daily, especially during:
   - 9:30 AM ET (market open)
   - 9:45 AM ET (ORB establishment)
   - 2:30 PM CST / 3:30 PM ET (end of day exit)
3. **Daily Pre-Market Check**: Verify NO positions exist in Alpaca before 9:30 AM
4. **Railway Replicas**: ALWAYS keep replicas = 1 (never increase)
5. **Version Control**: Use Git tags for production deployments
6. **Backup Plan**: Know how to manually close positions in Alpaca dashboard

## Cost Optimization

**Railway Pricing (as of 2024):**
- Free tier: $5 free credit/month
- Pro plan: $20/month

**To optimize:**
- Bot self-manages timing (only active 9:30 AM - 3:30 PM ET)
- Exits cleanly to avoid wasted compute time
- Bot stays alive outside trading hours and sleeps until the next session

## Emergency Shutdown

If you need to stop the bot immediately:

**Via Railway Dashboard:**
1. Go to your project
2. Click on the nvda-bot service
3. Click "Settings" → "Pause Service"

**Via Alpaca Dashboard:**
1. Log into Alpaca dashboard (https://app.alpaca.markets/paper/dashboard/overview)
2. Go to "Orders" → Cancel All
3. Go to "Positions" → Close All

## Maintenance

**Daily:**
- Check Railway logs for successful startup (before 9:30 AM ET)
- Verify ORB was established at 9:45 AM ET
- Confirm clean exit at 2:30 PM CST / 3:30 PM ET
- Check Alpaca dashboard: NO positions should exist after 3:30 PM ET

**Weekly:**
- Review trade history in Alpaca dashboard
- Analyze P&L and win rate
- Check for any unexpected position warnings

**Monthly:**
- Update `alpaca-py` if new version available
- Review strategy performance metrics
- Consider parameter adjustments if needed (stop %, profit target, etc.)

## Support

For issues:
- **Railway**: https://railway.app/help
- **Alpaca**: https://alpaca.markets/support
- **alpaca-py docs**: https://alpaca.markets/docs/python-sdk/

## Next Steps

1. **Test in paper trading for 1-2 weeks**
2. **Monitor daily exits at 2:30 PM CST / 3:30 PM ET**
3. **Verify no unexpected positions appear**
4. **After successful testing, switch to live trading:**
   - Change `paper=True` to `paper=False` in `nvda_strategy.py`
   - Commit and push to GitHub
   - Railway will auto-deploy
   - Monitor VERY closely for first 3 trading days
5. **Set up daily monitoring routine:**
   - 9:25 AM ET: Check Railway logs for bot startup
   - 9:45 AM ET: Verify ORB established
   - 3:35 PM ET: Confirm clean exit and no open positions
