# Financial RAG API Deployment Guide

## Quick Deploy Options

### 1. Docker Compose (Recommended for Testing)
```bash
# Set your API keys in .env file
echo "OPENAI_API_KEY=your-key-here" > .env

# Start all services
docker-compose up -d

# Access at http://localhost:8000
```

### 2. Docker Only
```bash
# Build
docker build -t financial-rag-api .

# Run
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=your-key \
  -e DATABASE_URL=your-db-url \
  -v $(pwd)/data:/app/data \
  financial-rag-api

# Access at http://localhost:8000
```

### 3. Railway.app (Easiest Cloud Deploy)
1. Fork this repo to your GitHub
2. Go to [Railway.app](https://railway.app)
3. Click "New Project" → "Deploy from GitHub"
4. Select this repo
5. Add environment variables in Railway dashboard
6. Get your endpoint: `https://your-app.railway.app`

### 4. Google Cloud Run
```bash
# Authenticate
gcloud auth login

# Set project
gcloud config set project YOUR-PROJECT-ID

# Build and deploy
gcloud run deploy financial-rag-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY=your-key

# Get endpoint URL from output
```

### 5. AWS Elastic Beanstalk
```bash
# Install EB CLI
pip install awsebcli

# Initialize
eb init -p docker financial-rag-api --region us-east-1

# Create environment
eb create financial-rag-env

# Deploy
eb deploy

# Get endpoint
eb status
```

### 6. Azure App Service
```bash
# Login
az login

# Create resource group
az group create --name FinancialRAG --location eastus

# Deploy
az webapp up \
  --name financial-rag-api \
  --runtime "PYTHON:3.12" \
  --sku B1

# Get endpoint
az webapp show --name financial-rag-api --query defaultHostName
```

### 7. Heroku
```bash
# Login
heroku login

# Create app
heroku create financial-rag-api

# Add buildpack
heroku buildpacks:set heroku/python

# Set config
heroku config:set OPENAI_API_KEY=your-key

# Deploy
git push heroku main

# Open
heroku open
```

### 8. DigitalOcean App Platform
1. Go to [DigitalOcean Apps](https://cloud.digitalocean.com/apps)
2. Click "Create App"
3. Connect GitHub repo
4. App Platform auto-detects Dockerfile
5. Add environment variables
6. Deploy

### 9. Render.com
1. Go to [Render.com](https://render.com)
2. New → Web Service
3. Connect GitHub repo
4. Render auto-detects Docker
5. Add environment variables
6. Deploy

### 10. Self-Hosted VPS (Production)
```bash
# On your server (Ubuntu/Debian)
sudo apt update
sudo apt install python3-pip python3-venv nginx certbot python3-certbot-nginx

# Clone repo
git clone https://github.com/YOUR-USERNAME/Financial_Rag_API.git
cd Financial_Rag_API

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn python-multipart

# Create systemd service
sudo nano /etc/systemd/system/financial-rag.service
```

Paste this:
```ini
[Unit]
Description=Financial RAG API
After=network.target

[Service]
User=YOUR-USERNAME
WorkingDirectory=/home/YOUR-USERNAME/Financial_Rag_API
Environment="PATH=/home/YOUR-USERNAME/Financial_Rag_API/venv/bin"
Environment="OPENAI_API_KEY=your-key"
Environment="DATABASE_URL=your-db-url"
ExecStart=/home/YOUR-USERNAME/Financial_Rag_API/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.core.server:app --bind 127.0.0.1:8000

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl enable financial-rag
sudo systemctl start financial-rag

# Configure Nginx
sudo nano /etc/nginx/sites-available/financial-rag
```

Paste this:
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/financial-rag /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Your API is now at https://your-domain.com
```

## Environment Variables Needed

Create a `.env` file:
```bash
OPENAI_API_KEY=sk-your-openai-key
DATABASE_URL=postgresql://user:password@host:5432/dbname
VECTOR_DB_DIR=./data/vectorstore
BGE_MODEL=BAAI/bge-large-en-v1.5
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
LLM_TEMPERATURE=0.7
```

## Cost Comparison

| Platform | Free Tier | Pricing | Best For |
|----------|-----------|---------|----------|
| Railway.app | $5 credit | ~$5-20/mo | Quick deploys |
| Heroku | Limited | $7-25/mo | Simple apps |
| Render.com | 750 hrs | $7-25/mo | Hobby projects |
| Google Cloud Run | 2M requests | Pay per use | Scalability |
| AWS EB | 1 year free | Variable | Enterprise |
| DigitalOcean | $200 credit | $5-50/mo | VPS control |
| VPS (Self) | - | $5-20/mo | Full control |

## Monitoring Your Endpoint

Once deployed, monitor your endpoint:
```bash
# Health check
curl https://your-endpoint.com/health

# Metrics
curl https://your-endpoint.com/metrics

# API docs
open https://your-endpoint.com/docs
```

## Recommended for This Project

**Best Choice: Railway.app or Google Cloud Run**
- Easy GitHub integration
- Auto-scaling
- Free tier available
- Good for RAG applications

**For Production: VPS with Nginx**
- Full control
- Best performance
- Cost-effective
- Professional setup
