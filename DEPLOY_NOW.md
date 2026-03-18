# Deploy to Railway NOW - Step-by-Step Guide

## 🚀 Let's Deploy Both Bots!

Your code is ready at: https://github.com/mbrimy77/Freedom-Bot

---

## Step 1: Open Railway and Login

1. **Open this link:** https://railway.app/new
2. Click **"Login with GitHub"**
3. Authorize Railway to access your repositories
4. You'll see the Railway dashboard

---

## Step 2: Create Project from GitHub

1. You should see **"Deploy from GitHub repo"** option
2. Click on it
3. A list of your repositories will appear
4. **Select:** `mbrimy77/Freedom-Bot`
5. Railway will create the project

---

## Step 3: Configure NVDA Bot (First Service)

Railway creates one service automatically. Let's set it up for NVDA:

### A. Rename the Service
1. Click on the service card (it might say "freedom-bot" or similar)
2. At the top, click the service name to rename
3. Change it to: **`nvda-bot`**

### B. Set Root Directory
1. Click **"Settings"** tab (left sidebar)
2. Scroll down to **"Root Directory"**
3. Enter: `/nvda_bot`
4. Changes auto-save

### C. Set Start Command
1. Still in Settings tab
2. Scroll to **"Start Command"**
3. Enter: `python nvda_strategy.py`
4. Changes auto-save

### D. Add Environment Variables
1. Click **"Variables"** tab (left sidebar)
2. Click **"+ New Variable"** or **"RAW Editor"**
3. Add these two variables:

```
ALPACA_API_KEY=YOUR_ACTUAL_API_KEY_HERE
ALPACA_SECRET_KEY=YOUR_ACTUAL_SECRET_KEY_HERE
```

Replace with your actual Alpaca keys!

### E. Deploy
1. Railway will automatically start deploying
2. Click **"Deployments"** tab to watch progress
3. Wait for **"✓ SUCCESS"** (takes 1-2 minutes)

---

## Step 4: Add MSOS Bot (Second Service)

Now let's add the second bot:

### A. Add New Service
1. Click the project name at the top to go back to project view
2. Click **"+ New"** button (top right)
3. Select **"GitHub Repo"**
4. Choose **`mbrimy77/Freedom-Bot`** again
5. Railway creates a second service card

### B. Rename the Service
1. Click on the new service card
2. Rename it to: **`msos-bot`**

### C. Set Root Directory
1. Click **"Settings"** tab
2. Scroll to **"Root Directory"**
3. Enter: `/msos_bot`

### D. Set Start Command
1. Still in Settings
2. Scroll to **"Start Command"**
3. Enter: `python momentum_bot.py`

### E. Add Environment Variables
1. Click **"Variables"** tab
2. Add the same two variables:

```
ALPACA_API_KEY=YOUR_ACTUAL_API_KEY_HERE
ALPACA_SECRET_KEY=YOUR_ACTUAL_SECRET_KEY_HERE
```

### F. Deploy
1. Railway auto-deploys
2. Check **"Deployments"** tab
3. Wait for **"✓ SUCCESS"**

---

## Step 5: Verify Both Bots Are Running

### Your Dashboard Should Show:

```
Freedom-Bot (Project)
├── nvda-bot ✓
│   Status: Active
│   /nvda_bot
│
└── msos-bot ✓
    Status: Active
    /msos_bot
```

---

## Step 6: Check the Logs

### NVDA Bot Logs:

1. Click on **nvda-bot** service
2. Click **"Deployments"** tab
3. Click the latest deployment
4. You should see:

```
[TIMESTAMP EST] NVDA ORB Bot initialized
[TIMESTAMP EST] Monitor Ticker: NVDA
[TIMESTAMP EST] Long Ticker: NVDL (2x)
[TIMESTAMP EST] Short Ticker: NVD (2x)
[TIMESTAMP EST] Account Size: $20,000
[TIMESTAMP EST] Paper Trading: Enabled
```

### MSOS Bot Logs:

1. Click on **msos-bot** service
2. Click **"Deployments"** tab
3. Click the latest deployment
4. You should see:

```
[TIMESTAMP CST] MOMENTUM TRADING BOT STARTED
[TIMESTAMP CST] Bot initialized
[TIMESTAMP CST] Monitor Ticker: MSOS
[TIMESTAMP CST] Trade Ticker: MSOX
[TIMESTAMP CST] Paper Trading: Enabled
```

---

## ✅ Deployment Complete!

Both bots are now running on Railway!

### What Happens Now?

**NVDA Bot (Morning Strategy):**
- Starts monitoring at 9:30 AM ET
- Establishes 15-minute Opening Range
- Trades from 9:45 AM - 2:00 PM CST
- **Golden Gap Exit at 2:00 PM CST**

**MSOS Bot (Afternoon Strategy):**
- Starts monitoring at 2:15 PM CST
- Trades from 2:15 PM - 2:30 PM CST (entry window)
- Hard exit at 2:58 PM CST

---

## 🔍 Monitoring Your Bots

### Check Logs Daily

**Morning (9:30 AM ET):**
- Check NVDA bot started
- Verify ORB established
- Watch for breakout signals

**Afternoon (2:00 PM CST):**
- Verify NVDA bot exited (Golden Gap)
- Check MSOS bot started at 2:15 PM
- Watch for momentum signals

### Railway Dashboard Tips

- **Green dot** = Service is running
- **Deployments** = See logs and history
- **Metrics** = CPU/Memory usage
- **Settings** = Change configuration

---

## 🚨 Common Issues & Fixes

### Build Failed
**Symptom:** Red X on deployment

**Fix:**
1. Check root directory is correct (`/nvda_bot` or `/msos_bot`)
2. Verify start command matches filename
3. Look at deployment logs for specific error

### Module Not Found
**Symptom:** Error says "No module named 'alpaca'"

**Fix:**
- Railway should auto-detect `requirements.txt`
- Check that `requirements.txt` exists in each folder
- Logs should show "Installing dependencies..."

### Bot Not Trading
**Symptom:** Bot runs but no trades

**This is normal for:**
- Paper trading mode (testing)
- No breakout signal triggered
- Outside trading windows
- Existing position already open

**To verify it's working:**
- Check logs for "Monitoring for signals..."
- Verify Alpaca API keys are correct
- Check Alpaca dashboard for account status

### Variables Not Working
**Symptom:** Error about missing ALPACA_API_KEY

**Fix:**
1. Go to service → Variables tab
2. Make sure both variables are listed
3. No quotes around values
4. Redeploy after adding variables

---

## 💰 Costs

**Estimated Monthly:**
- Hobby Plan: $5/month
- Usage: ~$3-5/month
- **Total: ~$10/month** for both bots

Railway charges per second of runtime. Since bots only run during market hours, costs are low.

---

## 📊 Next Steps

### 1. Monitor in Paper Trading (1-2 Weeks)
- [ ] Watch logs daily
- [ ] Verify Golden Gap exit (2:00 PM)
- [ ] Check capital available for MSOS bot
- [ ] Review trades in Alpaca dashboard

### 2. Track Performance
- Daily P&L by strategy
- Win rate
- Max drawdown
- Golden Gap exit times

### 3. Go Live When Ready
- Update both files: `paper=True` → `paper=False`
- Commit and push to GitHub
- Railway auto-redeploys
- Monitor closely for 3 days

---

## 🆘 Need Help?

**Railway Issues:**
- Discord: https://discord.gg/railway
- I can help troubleshoot!

**Alpaca Issues:**
- Check API keys are correct
- Verify account is funded
- Support: support@alpaca.markets

**Bot Issues:**
- Check GitHub repo: https://github.com/mbrimy77/Freedom-Bot
- Review logs for error messages
- I'm here to help!

---

## ✅ Checklist

After deployment, verify:

- [ ] Both services show green status
- [ ] NVDA bot logs show "initialized"
- [ ] MSOS bot logs show "initialized"
- [ ] Environment variables are set (both services)
- [ ] No red error messages in logs
- [ ] Can view deployment history
- [ ] Railway dashboard shows both services

---

## 🎯 You're All Set!

Your dual-strategy trading system is now live on Railway!

**Repository:** https://github.com/mbrimy77/Freedom-Bot
**Railway:** https://railway.app (your dashboard)

Both bots are running in paper trading mode. Monitor for 1-2 weeks, then switch to live trading when confident!

Good luck! 🚀📈
