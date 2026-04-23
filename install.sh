#!/bin/bash
echo "================================================"
echo "  CVIS AIOps Engine - Linux/macOS Installer"
echo "================================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found"
    exit 1
fi

echo "[OK] Python $(python3 --version) found"

# Install Redis
if command -v apt-get &> /dev/null; then
    sudo apt-get install -y redis-server
elif command -v brew &> /dev/null; then
    brew install redis
fi

# Install Python dependencies
pip3 install fastapi uvicorn psutil numpy scikit-learn torch pydantic redis aioredis aiofiles python-jose[cryptography] passlib bcrypt watchfiles

echo ""
echo "================================================"
echo "  Installation complete!"
echo "  Run CVIS with: python3 app.py"
echo "================================================"
