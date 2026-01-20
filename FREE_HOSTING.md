# Free Hosting Guide for Financial RAG API

## 🆓 Best Free Hosting Options (Ranked)

### 1. **Render.com** ⭐ RECOMMENDED
**Why**: Most generous free tier, easy setup, perfect for this project

**Free Tier:**
- 750 hours/month (enough for 24/7)
- 512MB RAM
- Sleeps after 15 min inactivity
- Free PostgreSQL database (90 days)

**Deploy Steps:**
1. Go to [render.com](https://render.com)
2. Sign up with GitHub
3. Click "New +" → "Web Service"
4. Connect this repository
5. Configure:
   - **Name**: financial-rag-api
   - **Runtime**: Docker
   - **Plan**: Free
6. Add Environment Variables:
   ```
   OPENAI_API_KEY=your-key-here
   PYTHON_VERSION=3.12
   ```
7. Click "Create Web Service"
8. Get your endpoint: `https://financial-rag-api.onrender.com`

**Your URL will be**: `https://[your-app-name].onrender.com`

---

### 2. **Railway.app** 
**Why**: $5 free credit, best developer experience

**Free Tier:**
- $5 credit/month (500 hours)
- No sleep mode
- Better performance than Render

**Deploy Steps:**
1. Go to [railway.app](https://railway.app)
2. Sign in with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select this repository
5. Railway auto-detects everything!
6. Add environment variables in dashboard:
   - `OPENAI_API_KEY`
7. Generate domain in Settings
8. Done! 🎉

**Your URL will be**: `https://[app-name].up.railway.app`

---

### 3. **Fly.io**
**Why**: 3 VMs free, always-on

**Free Tier:**
- 3 shared VMs free
- 160GB outbound bandwidth
- No cold starts

**Deploy Steps:**
1. Install flyctl:
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```
2. Login: `fly auth login`
3. Launch: `fly launch`
4. Deploy: `fly deploy`

**Your URL will be**: `https://[app-name].fly.dev`

---

### 4. **Koyeb**
**Why**: Free tier with no sleep

**Free Tier:**
- 2 services free
- Always-on (no sleep)
- Global CDN

**Deploy Steps:**
1. Go to [koyeb.com](https://koyeb.com)
2. Sign up with GitHub
3. "Create App" → "GitHub"
4. Select repository
5. Choose "Free" plan
6. Deploy!

**Your URL will be**: `https://[app-name].koyeb.app`

---

### 5. **Replit**
**Why**: Easiest for beginners

**Free Tier:**
- Free with some limitations
- Built-in IDE
- Good for development

**Deploy Steps:**
1. Go to [replit.com](https://replit.com)
2. Import from GitHub
3. Select this repository
4. Click "Run"
5. Done!

---

## 📝 Quick Comparison

| Platform | Free Hours | RAM | Sleep? | Database | Best For |
|----------|-----------|-----|---------|----------|----------|
| **Render** | 750hrs | 512MB | Yes (15min) | 90 days | Best free tier |
| **Railway** | $5 credit | 512MB | No | Paid | Developer UX |
| **Fly.io** | Always-on | 256MB | No | Included | Production-like |
| **Koyeb** | Always-on | 512MB | No | Extra | No sleep needs |
| **Replit** | Limited | 512MB | Yes | No | Quick testing |

---

## 🚀 My Recommendation: Use Render.com

It has the best free tier for your Financial RAG API. Here's why:
- ✅ 750 hours free (basically 24/7)
- ✅ Easy setup (3 clicks)
- ✅ Free PostgreSQL database
- ✅ Automatic HTTPS
- ✅ No credit card required

---

## 📋 Before Deploying - Checklist

1. **Set Environment Variables** (in hosting platform):
   ```bash
   OPENAI_API_KEY=sk-your-openai-key
   DATABASE_URL=auto-provided-by-host
   VECTOR_DB_DIR=/app/data/vectorstore
   ```

2. **Optional**: Add a free database
   - Render.com: Built-in free PostgreSQL
   - ElephantSQL: 20MB free PostgreSQL
   - Supabase: Free PostgreSQL with 500MB

3. **Cold Start Tip**: Free tiers sleep after inactivity
   - Use [UptimeRobot](https://uptimerobot.com) to ping your API every 5 minutes
   - Keeps your app awake (free monitoring)

---

## 🎯 Step-by-Step: Deploy to Render.com (Easiest)

### 1. Push to GitHub (if not already)
```bash
git add .
git commit -m "Ready for deployment"
git push origin main
```

### 2. Deploy on Render
1. Visit: https://render.com
2. Sign up with GitHub
3. Click "New +" → "Web Service"
4. Click "Connect Account" → Authorize GitHub
5. Find "Financial_Rag_API" in the list
6. Click "Connect"

### 3. Configure Settings
- **Name**: `financial-rag-api` (or your choice)
- **Region**: Choose closest to you
- **Branch**: `main`
- **Runtime**: **Docker** ← Important!
- **Plan**: **Free**

### 4. Add Environment Variable
Click "Advanced" → Add:
```
Key: OPENAI_API_KEY
Value: your-actual-openai-key
```

### 5. Create Web Service
Click "Create Web Service" button at bottom

### 6. Wait for Deploy (2-3 minutes)
Watch the logs as it builds and deploys

### 7. Get Your Endpoint! 🎉
```
https://financial-rag-api.onrender.com
```

### 8. Test Your API
```bash
# Health check
curl https://financial-rag-api.onrender.com/health

# API docs
open https://financial-rag-api.onrender.com/docs

# Chat endpoint
curl -X POST https://financial-rag-api.onrender.com/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"What is this API?"}'
```

---

## ⚡ Keep Your Free App Awake

Free tier apps sleep after 15 minutes of inactivity. To prevent this:

### Option 1: UptimeRobot (Free)
1. Go to [uptimerobot.com](https://uptimerobot.com)
2. Create free account
3. Add New Monitor:
   - Type: HTTP(s)
   - URL: `https://your-app.onrender.com/health`
   - Interval: 5 minutes
4. Your app stays awake! 🎉

### Option 2: Cron-job.org (Free)
1. Go to [cron-job.org](https://cron-job.org)
2. Create free account
3. Create cron job to ping your `/health` endpoint every 5 minutes

---

## 💰 Free Database Options

If you need a database:

1. **Supabase** (Best)
   - 500MB PostgreSQL free
   - https://supabase.com
   - No credit card needed

2. **ElephantSQL**
   - 20MB PostgreSQL free
   - https://elephantsql.com

3. **Render PostgreSQL**
   - Free for 90 days
   - Then $7/month

4. **PlanetScale** (MySQL)
   - 5GB free
   - https://planetscale.com

---

## 🔧 Troubleshooting Free Hosting

### Issue: App Crashes on Startup
**Solution**: Check logs, usually missing environment variables

### Issue: 502 Bad Gateway
**Solution**: App is starting (cold start), wait 30 seconds

### Issue: Out of Memory
**Solution**: Free tier has 512MB, optimize your code or upgrade

### Issue: App Sleeps Too Often
**Solution**: Use UptimeRobot to ping every 5 minutes

### Issue: Database Not Working
**Solution**: Check DATABASE_URL environment variable

---

## 🎉 You're Done!

Your Financial RAG API is now hosted for FREE at:
```
https://your-app-name.onrender.com
```

Share your API with:
- API Docs: `/docs`
- Dashboard: `/dashboard`
- Chat: `/api/v1/chat`
- Metrics: `/metrics`

---

## 📱 Next Steps

1. **Share your endpoint** with users
2. **Monitor uptime** with UptimeRobot
3. **Check metrics** at `/metrics`
4. **Read logs** in hosting platform dashboard
5. **Upgrade** when you outgrow free tier

**Questions?** Check hosting platform docs or contact support (all have great free tier support!)
