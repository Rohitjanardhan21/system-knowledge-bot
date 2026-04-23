@echo off
echo ================================================
echo   CVIS AIOps Engine - Windows Installer
echo ================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Download from https://python.org
    pause
    exit /b 1
)

echo [OK] Python found
echo.

:: Install dependencies
echo Installing dependencies...
pip install fastapi uvicorn psutil numpy scikit-learn torch pydantic redis aioredis aiofiles python-jose[cryptography] passlib bcrypt watchfiles

echo.
echo ================================================
echo   Installation complete!
echo   Run CVIS with: python app.py
echo ================================================
pause
