#!/bin/bash
echo "================================================"
echo "  CVIS AIOps Engine - Linux/macOS Installer"
echo "================================================"
echo ""

OS=$(uname -s)

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found"
    exit 1
fi
echo "[OK] $(python3 --version) found"

# Install Redis
if [ "$OS" = "Linux" ] && command -v apt-get &> /dev/null; then
    echo "Installing Redis..."
    sudo apt-get install -y redis-server > /dev/null 2>&1
    sudo systemctl enable redis-server > /dev/null 2>&1
    sudo systemctl start redis-server > /dev/null 2>&1
    echo "[OK] Redis installed"
elif [ "$OS" = "Darwin" ] && command -v brew &> /dev/null; then
    brew install redis > /dev/null 2>&1
    brew services start redis > /dev/null 2>&1
    echo "[OK] Redis installed"
fi

PACKAGES="fastapi uvicorn[standard] psutil numpy scikit-learn torch pydantic redis aioredis aiofiles python-jose[cryptography] passlib bcrypt watchfiles aiosqlite plyer"

if [ -d "venv" ]; then
    echo "Found existing venv — installing into it..."
    source venv/bin/activate
    pip install $PACKAGES --quiet
    echo "[OK] Dependencies installed into venv"
elif python3 -m venv --help > /dev/null 2>&1; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install $PACKAGES --quiet
    echo "[OK] Dependencies installed into venv"
else
    pip3 install --break-system-packages $PACKAGES --quiet
    echo "[OK] Dependencies installed"
fi

echo ""
echo "================================================"
echo "  Installation complete!"
echo ""
echo "  Run CVIS:"
echo "    source venv/bin/activate"
echo "    python3 app.py"
echo ""
echo "  Or with Docker:"
echo "    docker compose up -d"
echo ""
echo "  Dashboard: http://localhost:8000"
echo "================================================"
