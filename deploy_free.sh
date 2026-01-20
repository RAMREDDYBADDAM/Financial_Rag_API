#!/bin/bash
# One-Click Free Hosting Setup Script

echo "================================================"
echo "   Financial RAG API - Free Hosting Setup"
echo "================================================"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Choose your free hosting platform:${NC}"
echo "1) Render.com (Recommended - 750hrs free)"
echo "2) Railway.app ($5 credit)"
echo "3) Fly.io (Always-on free)"
echo "4) Manual setup"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
    1)
        echo ""
        echo -e "${GREEN}🚀 Deploying to Render.com...${NC}"
        echo ""
        echo "Steps:"
        echo "1. Visit: https://render.com"
        echo "2. Sign up with GitHub"
        echo "3. Click 'New +' → 'Web Service'"
        echo "4. Connect this repository: Financial_Rag_API"
        echo "5. Settings:"
        echo "   - Name: financial-rag-api"
        echo "   - Runtime: Docker"
        echo "   - Plan: Free"
        echo "6. Add Environment Variable:"
        echo "   - OPENAI_API_KEY = your-openai-key"
        echo "7. Click 'Create Web Service'"
        echo ""
        echo -e "${YELLOW}Your endpoint will be:${NC}"
        echo "https://financial-rag-api.onrender.com"
        echo ""
        echo "Opening Render.com in browser..."
        sleep 2
        python3 -m webbrowser "https://render.com" 2>/dev/null || xdg-open "https://render.com" 2>/dev/null || open "https://render.com" 2>/dev/null
        ;;
    
    2)
        echo ""
        echo -e "${GREEN}🚀 Deploying to Railway.app...${NC}"
        echo ""
        echo "Steps:"
        echo "1. Visit: https://railway.app"
        echo "2. Sign in with GitHub"
        echo "3. Click 'New Project' → 'Deploy from GitHub'"
        echo "4. Select: Financial_Rag_API"
        echo "5. Railway auto-detects everything!"
        echo "6. Add environment variable in dashboard:"
        echo "   - OPENAI_API_KEY"
        echo "7. Generate domain in Settings"
        echo ""
        echo -e "${YELLOW}Your endpoint will be:${NC}"
        echo "https://[app-name].up.railway.app"
        echo ""
        echo "Opening Railway.app in browser..."
        sleep 2
        python3 -m webbrowser "https://railway.app" 2>/dev/null || xdg-open "https://railway.app" 2>/dev/null || open "https://railway.app" 2>/dev/null
        ;;
    
    3)
        echo ""
        echo -e "${GREEN}🚀 Deploying to Fly.io...${NC}"
        echo ""
        echo "Installing flyctl..."
        
        # Check if flyctl is installed
        if command -v flyctl &> /dev/null; then
            echo "flyctl already installed ✓"
        else
            echo "Installing flyctl..."
            curl -L https://fly.io/install.sh | sh
            export FLYCTL_INSTALL="/home/$USER/.fly"
            export PATH="$FLYCTL_INSTALL/bin:$PATH"
        fi
        
        echo ""
        echo "Next steps:"
        echo "1. Run: flyctl auth login"
        echo "2. Run: flyctl launch"
        echo "3. Follow prompts (it will detect fly.toml)"
        echo "4. Set secrets: flyctl secrets set OPENAI_API_KEY=your-key"
        echo "5. Deploy: flyctl deploy"
        echo ""
        echo -e "${YELLOW}Your endpoint will be:${NC}"
        echo "https://[app-name].fly.dev"
        ;;
    
    4)
        echo ""
        echo -e "${GREEN}📖 Manual Setup${NC}"
        echo ""
        echo "Please read FREE_HOSTING.md for detailed instructions"
        echo ""
        if [ -f "FREE_HOSTING.md" ]; then
            cat FREE_HOSTING.md
        fi
        ;;
    
    *)
        echo ""
        echo -e "${YELLOW}Invalid choice. Please run again and select 1-4.${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}Setup complete! 🎉${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Next steps:"
echo "1. Follow the instructions above"
echo "2. Set your OPENAI_API_KEY environment variable"
echo "3. Deploy and get your endpoint URL"
echo "4. Test: curl https://your-endpoint.com/health"
echo "5. View docs: https://your-endpoint.com/docs"
echo ""
echo "Need help? Check FREE_HOSTING.md"
echo ""
