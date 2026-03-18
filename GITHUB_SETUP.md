# GitHub & Railway Setup Instructions

## ✅ What We've Done

1. ✅ Initialized Git repository
2. ✅ Organized files into `nvda_bot/` and `msos_bot/` folders
3. ✅ Created `.gitignore` files
4. ✅ Committed all files to Git
5. ⏳ Ready to push to GitHub

## 📋 Next Steps

### Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `trading-bots` (or your preferred name)
3. Description: "Dual-strategy automated trading system with NVDA ORB and MSOS momentum bots"
4. Choose: **Public** or **Private** (your choice)
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click "Create repository"

### Step 2: Copy the Repository URL

After creating the repo, GitHub will show you commands. Copy the repository URL:

**HTTPS (easier):**
```
https://github.com/YOUR_USERNAME/trading-bots.git
```

**SSH (if you have SSH keys set up):**
```
git@github.com:YOUR_USERNAME/trading-bots.git
```

### Step 3: We'll Push the Code

Once you provide the GitHub repo URL, I'll run:

```bash
git remote add origin YOUR_REPO_URL
git branch -M main
git push -u origin main
```

## 🚂 Railway Deployment (After GitHub Push)

### Step 1: Create Railway Account

1. Go to https://railway.app
2. Sign up with GitHub
3. Authorize Railway to access your repositories

### Step 2: Create New Project

1. Click "New Project"
2. Select "Deploy from GitHub repo"
3. Choose your `trading-bots` repository
4. Railway will detect the project

### Step 3: Configure NVDA Bot Service

1. Railway will create one service by default
2. Rename it to **`nvda-bot`**
3. Go to **Settings** tab:
   - **Root Directory**: `/nvda_bot`
   - **Start Command**: `python nvda_strategy.py`
4. Go to **Variables** tab:
   - Add `ALPACA_API_KEY`: (your Alpaca API key)
   - Add `ALPACA_SECRET_KEY`: (your Alpaca secret key)
5. Click "Deploy"

### Step 4: Add MSOS Bot Service

1. In the same project, click **"+ New"** → **"Service"**
2. Choose **"GitHub Repo"** → Select your `trading-bots` repo again
3. Name it **`msos-bot`**
4. Go to **Settings** tab:
   - **Root Directory**: `/msos_bot`
   - **Start Command**: `python momentum_bot.py`
5. Go to **Variables** tab:
   - Add `ALPACA_API_KEY`: (same as above)
   - Add `ALPACA_SECRET_KEY`: (same as above)
6. Click "Deploy"

### Step 5: Verify Deployment

**Check NVDA Bot Logs:**
```
[TIMESTAMP] NVDA ORB Bot initialized
[TIMESTAMP] Monitor Ticker: NVDA
[TIMESTAMP] Establishing 15-minute Opening Range...
```

**Check MSOS Bot Logs:**
```
[TIMESTAMP] Bot initialized
[TIMESTAMP] Monitor Ticker: MSOS
[TIMESTAMP] Fetching previous close for MSOS...
```

## 📊 Railway Dashboard

Your Railway project will look like this:

```
trading-bots (Project)
├── nvda-bot (Service)
│   ├── Root: /nvda_bot
│   ├── Start: python nvda_strategy.py
│   └── Runs: 9:30 AM - 2:00 PM CST
└── msos-bot (Service)
    ├── Root: /msos_bot
    ├── Start: python momentum_bot.py
    └── Runs: 2:15 PM - 2:58 PM CST
```

## 🔧 Troubleshooting

**Build Failed:**
- Check that root directory is set correctly
- Verify start command matches file name
- Check environment variables are set

**Bot Not Starting:**
- Review logs for error messages
- Verify Alpaca API keys are correct
- Check if Railway detected `requirements.txt`

**Golden Gap Not Working:**
- Verify NVDA bot exits at 2:00 PM CST (check logs)
- Ensure MSOS bot starts at 2:15 PM CST
- Check timezone settings in Railway (should auto-detect UTC)

## 💰 Railway Pricing

- **Free Tier**: $5 credit/month (good for testing)
- **Hobby Plan**: $5/month + usage
- **Pro Plan**: $20/month + usage

Both bots should fit within the Hobby plan easily.

## 📝 Next Steps After Deployment

1. Monitor logs for first few days
2. Verify Golden Gap exit at 2:00 PM daily
3. Check Alpaca dashboard for trades
4. Track P&L in spreadsheet
5. Switch to live trading when confident (change `paper=True` to `paper=False`)

---

**Ready to push to GitHub?** Just provide your GitHub repository URL and I'll push the code!
