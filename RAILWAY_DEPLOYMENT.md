# Railway Deployment Guide - Step by Step

## ✅ GitHub Push Complete!

Your code is now at: https://github.com/mbrimy77/MSOS---Freedom

The repository now contains:
- ✅ NVDA Bot (`/nvda_bot/`)
- ✅ MSOS Bot (`/msos_bot/`)
- ✅ Complete documentation
- ✅ Real-time trade monitoring for both bots

---

## 🚂 Railway Deployment Instructions

### Step 1: Access Railway

1. Go to https://railway.app
2. Click "Login" → "Login with GitHub"
3. Authorize Railway to access your repositories

### Step 2: Create New Project

1. Click "**New Project**" button (top right)
2. Select "**Deploy from GitHub repo**"
3. Choose `mbrimy77/MSOS---Freedom` from the list
4. Railway will start creating the project

### Step 3: Configure NVDA Bot (First Service)

Railway will create one service automatically. Let's configure it for the NVDA bot:

**A. Service Settings:**
1. Click on the service card
2. Click "**Settings**" tab
3. Rename service to: `nvda-bot`
4. Scroll to "**Root Directory**"
   - Enter: `/nvda_bot`
5. Scroll to "**Start Command**"
   - Enter: `python nvda_strategy.py`
6. Click "**Save**" or changes auto-save

**B. Environment Variables:**
1. Click "**Variables**" tab
2. Click "**+ New Variable**"
3. Add these two variables:
   
   **Variable 1:**
   - Key: `ALPACA_API_KEY`
   - Value: `[Your Alpaca API Key]`
   
   **Variable 2:**
   - Key: `ALPACA_SECRET_KEY`
   - Value: `[Your Alpaca Secret Key]`

4. Variables auto-save when you enter them

**C. Deploy:**
- Railway will automatically deploy after you set the root directory
- Check the "**Deployments**" tab to see progress
- Wait for "✓ SUCCESS" status

### Step 4: Add MSOS Bot (Second Service)

Now let's add the MSOS bot as a second service:

**A. Add New Service:**
1. Go back to project view (click project name at top)
2. Click "**+ New**" button
3. Select "**GitHub Repo**"
4. Choose `mbrimy77/MSOS---Freedom` again (yes, same repo!)
5. Railway creates a second service

**B. Service Settings:**
1. Click on the new service card
2. Click "**Settings**" tab
3. Rename service to: `msos-bot`
4. Scroll to "**Root Directory**"
   - Enter: `/msos_bot`
5. Scroll to "**Start Command**"
   - Enter: `python momentum_bot.py`
6. Changes auto-save

**C. Environment Variables:**
1. Click "**Variables**" tab
2. Add the same two variables:
   
   **Variable 1:**
   - Key: `ALPACA_API_KEY`
   - Value: `[Your Alpaca API Key]`
   
   **Variable 2:**
   - Key: `ALPACA_SECRET_KEY`
   - Value: `[Your Alpaca Secret Key]`

**D. Deploy:**
- Railway auto-deploys
- Check "**Deployments**" tab for status
- Wait for "✓ SUCCESS"

### Step 5: Verify Both Bots Are Running

**Your Railway Dashboard should now show:**

```
MSOS---Freedom (Project)
├── nvda-bot (Service)
│   ├── Status: Deployed
│   ├── Root: /nvda_bot
│   └── Command: python nvda_strategy.py
└── msos-bot (Service)
    ├── Status: Deployed
    ├── Root: /msos_bot
    └── Command: python momentum_bot.py
```

### Step 6: Check Logs

**NVDA Bot Logs (should show):**
```
[TIMESTAMP EST] NVDA ORB Bot initialized
[TIMESTAMP EST] Monitor Ticker: NVDA
[TIMESTAMP EST] Long Ticker: NVDL (2x)
[TIMESTAMP EST] Short Ticker: NVD (2x)
[TIMESTAMP EST] Account Size: $20,000
[TIMESTAMP EST] Paper Trading: Enabled
[TIMESTAMP EST] Establishing 15-minute Opening Range...
```

**MSOS Bot Logs (should show):**
```
[TIMESTAMP CST] MOMENTUM TRADING BOT STARTED
[TIMESTAMP CST] Bot initialized
[TIMESTAMP CST] Monitor Ticker: MSOS
[TIMESTAMP CST] Trade Ticker: MSOX
[TIMESTAMP CST] Paper Trading: Enabled
[TIMESTAMP CST] Fetching previous close for MSOS...
```

---

## 🕐 Bot Schedules

Both bots will run continuously but only trade during their windows:

| Time | NVDA Bot | MSOS Bot |
|------|----------|----------|
| 9:30 AM ET | Establishes ORB | Idle |
| 9:45 AM - 2:00 PM CST | Trading window | Idle |
| 2:00 PM CST | **GOLDEN GAP EXIT** | Idle |
| 2:00 - 2:15 PM CST | Stopped | Buffer (15 min) |
| 2:15 PM CST | Stopped | Starts monitoring |
| 2:15 - 2:58 PM CST | Stopped | Trading window |
| 2:58 PM CST | Stopped | Exits |

---

## 🔧 Troubleshooting

### Build Failed

**Problem:** Railway shows "Build Failed" or "Deployment Failed"

**Solutions:**
1. Check that root directory is set:
   - NVDA: `/nvda_bot`
   - MSOS: `/msos_bot`
2. Verify start command:
   - NVDA: `python nvda_strategy.py`
   - MSOS: `python momentum_bot.py`
3. Check deployment logs for specific error

### Module Not Found

**Problem:** Error says "ModuleNotFoundError: No module named 'alpaca'"

**Solution:**
- Railway should auto-detect `requirements.txt`
- If not, add a custom build command:
  - Settings → Build Command: `pip install -r requirements.txt`

### Environment Variables Missing

**Problem:** Bot crashes with "ALPACA_API_KEY not found"

**Solution:**
1. Go to Variables tab
2. Verify both variables are set:
   - `ALPACA_API_KEY`
   - `ALPACA_SECRET_KEY`
3. Redeploy after adding variables

### Bot Not Trading

**Problem:** Bot starts but no trades execute

**Possible Causes:**
1. Outside trading window (check times)
2. Paper trading mode (expected - test first!)
3. No breakout/momentum signal triggered
4. Existing position already (check Alpaca dashboard)

**Solutions:**
- Check logs for "Monitoring for signals..." message
- Verify market is open (9:30 AM - 4:00 PM ET)
- Check Alpaca dashboard for account status

### Golden Gap Not Working

**Problem:** MSOS bot says "insufficient buying power" at 2:15 PM

**Solutions:**
1. Verify NVDA bot closed at 2:00 PM CST (check logs)
2. Check Alpaca settlement status
3. Increase buffer (change GOLDEN_GAP_EXIT to 1:55 PM)

---

## 💰 Railway Costs

**Estimated Monthly Cost:**
- Free tier: $5 credit (good for testing ~5 days)
- Hobby plan: $5/month + ~$3-5 usage = **~$10/month total**

Both bots combined:
- ~8 hours/day runtime
- Low compute usage (just data streams)
- Should be well under $15/month

---

## 📊 Monitoring & Maintenance

### Daily Checklist

**Before Market Open (9:00 AM ET):**
- [ ] Check Railway dashboard (both services running)
- [ ] Verify Alpaca API accessible
- [ ] Confirm $20k buying power available

**During Trading:**
- [ ] Monitor NVDA bot logs (9:30 AM - 2:00 PM CST)
- [ ] Verify Golden Gap exit at 2:00 PM CST
- [ ] Monitor MSOS bot logs (2:15 PM - 2:58 PM CST)

**After Market Close:**
- [ ] Review trades in Alpaca dashboard
- [ ] Check both bots exited cleanly
- [ ] Log daily P&L

### Weekly Review

1. Check Railway logs for errors
2. Review win rate for each strategy
3. Verify Golden Gap timing is consistent
4. Update position sizing if needed

---

## 🎯 Next Steps

### 1. Test in Paper Trading (1-2 Weeks)

- [ ] Run both bots for at least 5 trading days
- [ ] Verify Golden Gap works correctly
- [ ] Check capital is available for MSOS at 2:15 PM
- [ ] Review all logs daily

### 2. Monitor Key Metrics

Track in a spreadsheet:
- Daily P&L by strategy
- Win rate
- Average win/loss
- Max drawdown
- Golden Gap exit times

### 3. Go Live (When Ready)

**To switch to live trading:**

1. Update both bot files:
   - Change `paper=True` to `paper=False`
   
2. Commit and push to GitHub:
   ```bash
   git add nvda_bot/nvda_strategy.py msos_bot/momentum_bot.py
   git commit -m "Switch to live trading"
   git push
   ```

3. Railway will auto-redeploy both services

4. Monitor closely for first 3 days

---

## 🆘 Emergency Shutdown

**If you need to stop trading immediately:**

### Option 1: Railway Dashboard
1. Go to Railway project
2. Click on service → Settings
3. Click "**Pause Service**" for both bots

### Option 2: Alpaca Dashboard
1. Log into Alpaca
2. Orders → "Cancel All"
3. Positions → "Close All"

### Option 3: Delete Service
- In Railway, Settings → "Remove Service" (drastic!)

---

## 📞 Support

**Railway Support:**
- Discord: https://discord.gg/railway
- Docs: https://docs.railway.app/

**Alpaca Support:**
- Email: support@alpaca.markets
- Docs: https://alpaca.markets/docs/

**GitHub Issues:**
- Create issue at: https://github.com/mbrimy77/MSOS---Freedom/issues

---

## ✅ Deployment Complete!

You now have:
- ✅ Code pushed to GitHub
- 🚂 Ready to deploy to Railway (follow steps above)
- 📊 Two independent bots with Golden Gap coordination
- 📈 Real-time trade monitoring for accurate stops
- 📚 Complete documentation

**Start with Railway Step 1 above and deploy both services!**

Good luck with your automated trading system! 🎯📈
