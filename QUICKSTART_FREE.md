# 🆓 Quick Start: Free Hosting in 3 Minutes

## ⚡ Fastest Option: Render.com

### Step 1: Prepare (30 seconds)
```bash
# Make sure code is pushed to GitHub
git add .
git commit -m "Ready for deployment"
git push origin main
```

### Step 2: Deploy (2 minutes)
1. Go to **https://render.com**
2. Click **"Get Started for Free"**
3. Sign up with **GitHub**
4. Click **"New +"** → **"Web Service"**
5. Click **"Connect Account"** → Authorize GitHub
6. Find **"Financial_Rag_API"** → Click **"Connect"**

### Step 3: Configure (30 seconds)
```
Name: financial-rag-api
Region: [Choose closest]
Branch: main
Runtime: Docker          ← IMPORTANT!
Plan: Free              ← IMPORTANT!
```

**Environment Variables** (click "Advanced"):
```
OPENAI_API_KEY = sk-your-openai-key-here
```

### Step 4: Launch 🚀
Click **"Create Web Service"** at the bottom

Wait 2-3 minutes... ☕

### Step 5: Get Your Endpoint! 🎉
```
https://financial-rag-api.onrender.com
```

---

## 🧪 Test Your Deployment

```bash
# Health check
curl https://your-app.onrender.com/health

# View API docs
open https://your-app.onrender.com/docs

# Test chat endpoint
curl -X POST https://your-app.onrender.com/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test",
    "question": "What can you do?"
  }'
```

---

## 🎯 Alternative: Railway.app (Better Performance)

### If you prefer Railway ($5 free credit, faster):

1. Go to **https://railway.app**
2. Sign in with **GitHub**
3. **"New Project"** → **"Deploy from GitHub repo"**
4. Select **Financial_Rag_API**
5. Railway auto-detects everything! ✨
6. Settings → **"Generate Domain"**
7. Add **OPENAI_API_KEY** in Variables tab
8. Done! Get URL from dashboard

Your endpoint: `https://[random].up.railway.app`

---

## 🔥 Pro Tips

### Keep Your Free App Awake
Free apps sleep after 15 min inactivity. Prevent this:

**Option 1: UptimeRobot** (Recommended)
1. Sign up at https://uptimerobot.com (free)
2. Add New Monitor:
   - Type: HTTP(s)
   - URL: `https://your-app.onrender.com/health`
   - Interval: 5 minutes
3. Done! App stays awake 24/7 🎉

**Option 2: GitHub Actions** (Advanced)
Create `.github/workflows/keep-alive.yml`:
```yaml
name: Keep Alive
on:
  schedule:
    - cron: '*/5 * * * *'  # Every 5 minutes
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: curl https://your-app.onrender.com/health
```

### Add Free Database
If you need PostgreSQL:

**Supabase** (Best free tier):
1. Go to https://supabase.com
2. Create project (free)
3. Get connection string
4. Add to Render as `DATABASE_URL` env var

---

## 📊 What You Get (Free Tier)

### Render.com
- ✅ 750 hours/month (31 days!)
- ✅ 512MB RAM
- ✅ Free SSL (HTTPS)
- ✅ Automatic deploys from GitHub
- ✅ Free PostgreSQL (90 days)
- ⚠️ Sleeps after 15 min inactivity

### Railway.app
- ✅ $5 credit/month (~500 hours)
- ✅ 512MB RAM
- ✅ No sleep mode
- ✅ Better performance
- ✅ Automatic deploys
- ⚠️ Credit runs out if used 24/7

---

## 🎉 You're Live!

Your Financial RAG API is now hosted at:
```
🌐 https://your-app-name.onrender.com
```

**Share these endpoints:**
- 📖 API Docs: `/docs`
- 💬 Chat: `/api/v1/chat`
- 📊 Dashboard: `/dashboard`
- 🏥 Health: `/health`
- 📈 Metrics: `/metrics`

---

## 🆘 Troubleshooting

**App won't start?**
- Check logs in Render dashboard
- Verify OPENAI_API_KEY is set correctly
- Make sure Docker is selected as runtime

**502 Bad Gateway?**
- App is waking up from sleep (wait 30 seconds)
- Or app crashed (check logs)

**Out of memory?**
- Free tier has 512MB limit
- Optimize code or upgrade to paid tier

**Database issues?**
- Check DATABASE_URL environment variable
- Verify database is created and accessible

---

## 💬 Need Help?

1. Check logs in your hosting dashboard
2. Read [FREE_HOSTING.md](FREE_HOSTING.md) for details
3. Join hosting platform Discord/forum
4. All platforms have great free support!

---

## 🚀 Ready to Deploy?

Run this command:
```bash
./deploy_free.sh
```

Or follow the steps above manually.

**Happy hosting! 🎉**
