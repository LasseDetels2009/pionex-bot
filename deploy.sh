#!/bin/bash

# Pionex Futures Grid Bot Cloud Deployment Script
# Supports: AWS, Google Cloud, DigitalOcean, Azure, VPS

set -e

echo "🚀 Pionex Futures Grid Bot Cloud Deployment"
echo "============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[HEADER]${NC} $1"
}

# Check if .env file exists
if [ ! -f .env ]; then
    print_error ".env file not found! Please create it from env.example"
    echo "cp env.example .env"
    echo "Then edit .env with your API keys and configuration"
    exit 1
fi

# Function to deploy to different cloud providers
deploy_aws() {
    print_header "Deploying to AWS EC2..."
    
    # Install Docker on Ubuntu
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose
    
    # Start Docker service
    sudo systemctl start docker
    sudo systemctl enable docker
    
    # Add user to docker group
    sudo usermod -aG docker $USER
    
    # Build and run with docker-compose
    sudo docker-compose up -d --build
    
    print_status "Bot deployed on AWS EC2!"
    print_status "Access Grafana: http://your-ip:3000 (admin/admin123)"
    print_status "Access Prometheus: http://your-ip:9090"
}

deploy_digitalocean() {
    print_header "Deploying to DigitalOcean Droplet..."
    
    # Install Docker
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    
    # Install Docker Compose
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    
    # Build and run
    sudo docker-compose up -d --build
    
    print_status "Bot deployed on DigitalOcean!"
}

deploy_google_cloud() {
    print_header "Deploying to Google Cloud Platform..."
    
    # Install Docker
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose
    
    # Start Docker
    sudo systemctl start docker
    sudo systemctl enable docker
    
    # Build and run
    sudo docker-compose up -d --build
    
    print_status "Bot deployed on Google Cloud!"
}

deploy_azure() {
    print_header "Deploying to Azure VM..."
    
    # Install Docker
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose
    
    # Start Docker
    sudo systemctl start docker
    sudo systemctl enable docker
    
    # Build and run
    sudo docker-compose up -d --build
    
    print_status "Bot deployed on Azure!"
}

deploy_vps() {
    print_header "Deploying to VPS..."
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        print_status "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $USER
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        print_status "Installing Docker Compose..."
        sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
    fi
    
    # Build and run
    sudo docker-compose up -d --build
    
    print_status "Bot deployed on VPS!"
}

# Function to setup monitoring
setup_monitoring() {
    print_header "Setting up monitoring..."
    
    # Create monitoring directories
    mkdir -p monitoring/grafana/dashboards
    mkdir -p monitoring/grafana/datasources
    mkdir -p logs
    
    # Create Prometheus config
    cat > monitoring/prometheus.yml << EOF
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'pionex-bot'
    static_configs:
      - targets: ['pionex-bot:5000']
    metrics_path: '/metrics'
EOF

    # Create Grafana datasource
    cat > monitoring/grafana/datasources/prometheus.yml << EOF
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
EOF

    print_status "Monitoring setup complete!"
}

# Function to setup SSL with Let's Encrypt
setup_ssl() {
    print_header "Setting up SSL certificate..."
    
    # Install certbot
    sudo apt-get update
    sudo apt-get install -y certbot
    
    # Get domain from user
    read -p "Enter your domain name: " DOMAIN
    
    # Get SSL certificate
    sudo certbot certonly --standalone -d $DOMAIN
    
    # Update docker-compose with SSL
    cat > docker-compose.ssl.yml << EOF
version: '3.8'

services:
  nginx:
    image: nginx:alpine
    container_name: nginx-proxy
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - /etc/letsencrypt:/etc/letsencrypt:ro
    depends_on:
      - pionex-bot
    networks:
      - bot-network

  pionex-bot:
    build: .
    container_name: pionex-futures-bot
    restart: unless-stopped
    expose:
      - "5000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - TELEGRAM_BOT_TOKEN=\${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=\${TELEGRAM_CHAT_ID}
      - BINANCE_API_KEY=\${BINANCE_API_KEY}
      - BINANCE_SECRET_KEY=\${BINANCE_SECRET_KEY}
      - PIONEX_API_KEY=\${PIONEX_API_KEY}
      - PIONEX_SECRET_KEY=\${PIONEX_SECRET_KEY}
      - WEBHOOK_URL=https://$DOMAIN/webhook
    env_file:
      - .env
    networks:
      - bot-network

networks:
  bot-network:
    driver: bridge
EOF

    # Create nginx config
    cat > nginx.conf << EOF
events {
    worker_connections 1024;
}

http {
    upstream pionex-bot {
        server pionex-bot:5000;
    }

    server {
        listen 80;
        server_name $DOMAIN;
        return 301 https://\$server_name\$request_uri;
    }

    server {
        listen 443 ssl;
        server_name $DOMAIN;

        ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

        location / {
            proxy_pass http://pionex-bot;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
        }
    }
}
EOF

    print_status "SSL setup complete! Use docker-compose.ssl.yml for SSL deployment"
}

# Function to show status
show_status() {
    print_header "Bot Status:"
    sudo docker-compose ps
    
    print_header "Recent Logs:"
    sudo docker-compose logs --tail=20 pionex-bot
}

# Function to stop bot
stop_bot() {
    print_header "Stopping bot..."
    sudo docker-compose down
    print_status "Bot stopped!"
}

# Function to restart bot
restart_bot() {
    print_header "Restarting bot..."
    sudo docker-compose restart
    print_status "Bot restarted!"
}

# Function to update bot
update_bot() {
    print_header "Updating bot..."
    git pull
    sudo docker-compose down
    sudo docker-compose up -d --build
    print_status "Bot updated!"
}

# Main menu
show_menu() {
    echo ""
    echo "Choose deployment option:"
    echo "1) Deploy to AWS EC2"
    echo "2) Deploy to DigitalOcean Droplet"
    echo "3) Deploy to Google Cloud Platform"
    echo "4) Deploy to Azure VM"
    echo "5) Deploy to VPS (Generic)"
    echo "6) Setup monitoring"
    echo "7) Setup SSL certificate"
    echo "8) Show bot status"
    echo "9) Stop bot"
    echo "10) Restart bot"
    echo "11) Update bot"
    echo "12) Exit"
    echo ""
}

# Main script
main() {
    print_header "Pionex Futures Grid Bot Cloud Deployment"
    
    # Check if running as root
    if [ "$EUID" -eq 0 ]; then
        print_warning "Running as root is not recommended for security reasons"
    fi
    
    # Setup monitoring by default
    setup_monitoring
    
    while true; do
        show_menu
        read -p "Enter your choice (1-12): " choice
        
        case $choice in
            1) deploy_aws ;;
            2) deploy_digitalocean ;;
            3) deploy_google_cloud ;;
            4) deploy_azure ;;
            5) deploy_vps ;;
            6) setup_monitoring ;;
            7) setup_ssl ;;
            8) show_status ;;
            9) stop_bot ;;
            10) restart_bot ;;
            11) update_bot ;;
            12) print_status "Goodbye!"; exit 0 ;;
            *) print_error "Invalid option. Please try again." ;;
        esac
        
        echo ""
        read -p "Press Enter to continue..."
    done
}

# Run main function
main 