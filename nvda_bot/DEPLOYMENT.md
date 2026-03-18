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
├── msos_bot/
│   ├── momentum_bot.py
│   └── requirements.txt
├── nvda_bot/
│   ├── nvda_strategy.py
│   ├── requirements.txt
│   ├── README.md
│   └── .gitignore
└── README.md
```

Push both folders to GitHub:

```bash
git add msos_bot/ nvda_bot/
git commit -m "Add NVDA and MSOS trading bots"
git push origin main
```

### 2. Create Railway Projects

#### Option A: Single Project, Two Services (Recommended)

1. Go to Railway dashboard
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your repository

**Create NVDA Service:**
- Click "Add Service" → "GitHub Repo"
- **Service Name**: `nvda-bot`
- **Settings** → **Root Directory**: `/nvda_bot`
- **Settings** → **Start Command**: `python nvda_strategy.py`
- **Variables** tab:
  - Add `ALPACA_API_KEY`: (your key)
  - Add `ALPACA_SECRET_KEY`: (your secret)

**Create MSOS Service:**
- Click "Add Service" → "GitHub Repo"  
- **Service Name**: `msos-bot`
- **Settings** → **Root Directory**: `/msos_bot`
- **Settings** → **Start Command**: `python momentum_bot.py`
- **Variables** tab:
  - Add `ALPACA_API_KEY`: (your key)
  - Add `ALPACA_SECRET_KEY`: (your secret)

#### Option B: Two Separate Projects

Create two separate Railway projects (one for NVDA, one for MSOS) and configure each with the appropriate root directory.

### 3. Configure Environment Variables

For each service, add these environment variables in Railway:

```
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
```

### 4. Deployment Settings

**NVDA Bot Settings:**
- **Runtime**: Python 3.11+
- **Root Directory**: `/nvda_bot`
- **Start Command**: `python nvda_strategy.py`
- **Region**: Choose closest to your location

**MSOS Bot Settings:**
- **Runtime**: Python 3.11+
- **Root Directory**: `/msos_bot`
- **Start Command**: `python momentum_bot.py`
- **Region**: Same as NVDA bot

### 5. Verify Deployment

After deployment, check the logs:

**NVDA Bot should show:**
```
[TIMESTAMP] NVDA ORB Bot initialized
[TIMESTAMP] Monitor Ticker: NVDA
[TIMESTAMP] Long Ticker: NVDL (2x)
[TIMESTAMP] Short Ticker: NVD (2x)
[TIMESTAMP] Establishing 15-minute Opening Range...
```

**MSOS Bot should show:**
```
[TIMESTAMP] Bot initialized
[TIMESTAMP] Monitor Ticker: MSOS
[TIMESTAMP] Trade Ticker: MSOX
[TIMESTAMP] Fetching previous close...
```

### 6. Monitor the "Golden Gap"

Watch the NVDA bot logs around 2:00 PM CST:

```
[2026-03-17 14:00:00 CST] CLOSING ALL POSITIONS - GOLDEN GAP EXIT at 2026-03-17 14:00:00 CST
[2026-03-17 14:00:00 CST] ✓ Closed position: NVDL
[2026-03-17 14:00:00 CST] ✓ All pending orders canceled
[2026-03-17 14:00:01 CST] Golden Gap exit time reached. Bot stopping.
```

Then verify MSOS bot activates at 2:15 PM CST:

```
[2026-03-17 14:15:00 CT] Subscribed to MSOS live trade stream
[2026-03-17 14:15:00 CT] Monitoring for signals...
```

## Troubleshooting

### Bot Doesn't Start

**Check:**
- Root directory is set correctly (`/nvda_bot` or `/msos_bot`)
- Start command is correct (`python nvda_strategy.py`)
- Environment variables are set
- `requirements.txt` exists in the root directory

### "Module Not Found" Error

Railway should auto-install from `requirements.txt`. If not:
- Add a `Procfile` (though not typically needed):
  ```
  worker: pip install -r requirements.txt && python nvda_strategy.py
  ```

### Golden Gap Not Working

**Verify:**
- Bot timezone settings (CST = America/Chicago)
- System time on Railway (should be UTC, bot converts internally)
- Check logs for exact exit timestamp

### Position Not Closing Before MSOS Bot

**Solutions:**
1. Increase buffer: Change `GOLDEN_GAP_EXIT` to `time(13, 55)` (1:55 PM CST)
2. Add manual check in MSOS bot to verify buying power before entry
3. Monitor Alpaca account settlement times

## Best Practices

1. **Paper Trading First**: Test both bots in paper mode for at least 1 week
2. **Monitor Logs**: Check Railway logs daily for the first week
3. **Capital Management**: Ensure $20k is available at 2:15 PM CST daily
4. **Backup Alerts**: Set up alerts (email/SMS) for bot failures
5. **Version Control**: Use Git tags for production deployments

## Cost Optimization

**Railway Pricing (as of 2024):**
- Free tier: $5 free credit/month
- Pro plan: $20/month for both services

**To optimize:**
- Both services can share one Railway project
- Bots only run during market hours (saves compute time)
- Consider scheduling (though Railway doesn't natively support cron, bots self-manage timing)

## Emergency Shutdown

If you need to stop both bots immediately:

**Via Railway Dashboard:**
1. Go to your project
2. Click on each service
3. Click "Settings" → "Pause Service"

**Via Alpaca API:**
1. Log into Alpaca dashboard
2. Go to "Orders" → Cancel All
3. Go to "Positions" → Close All

## Maintenance

**Daily:**
- Check logs for errors
- Verify both bots started/stopped correctly

**Weekly:**
- Review trade history in Alpaca
- Check P&L by strategy
- Verify Golden Gap timing logs

**Monthly:**
- Update `alpaca-py` if new version available
- Review strategy performance
- Adjust position sizing if needed

## Support

For issues:
- **Railway**: https://railway.app/help
- **Alpaca**: https://alpaca.markets/support
- **alpaca-py docs**: https://alpaca.markets/docs/python-sdk/

## Next Steps

1. Test in paper trading for 1 week
2. Monitor Golden Gap exits daily
3. Verify capital availability for MSOS bot
4. After successful testing, switch to live trading:
   - Change `paper=True` to `paper=False` in both bots
   - Redeploy to Railway
   - Monitor closely for first 3 days
