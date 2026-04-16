#!/bin/bash

# HD Dashboard Setup Script

echo "🚀 Starting setup for Next Hemodialysis Dashboard..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# Create necessary directories
echo "Creating templates and static directories..."
mkdir -p templates static

# Check if dashboard.html is in the right place
if [ -f "dashboard.html" ]; then
    mv dashboard.html templates/dashboard.html
fi

# Create basic .env if it doesn't exist
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo ".env created from .env.example"
    else
        echo "DATABASE_URL=sqlite:///./hd_dashboard.db" > .env
        echo "TWILIO_ACCOUNT_SID=your_sid" >> .env
        echo "TWILIO_AUTH_TOKEN=your_token" >> .env
        echo "TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886" >> .env
        echo ".env created with default sqlite settings"
    fi
fi

echo "✅ Setup complete!"
echo ""
echo "To start the dashboard server, run:"
echo "source venv/bin/activate && uvicorn main:app --reload"
