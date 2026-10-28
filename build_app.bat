@echo off
cd /d "%~dp0"
echo ============================================================
echo   CVIS Desktop App Builder
echo ============================================================
echo.

:: Install required packages
echo [1/5] Installing backend dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Python backend dependencies could not be installed.
    pause
    exit /b 1
)

echo [2/5] Installing desktop build dependencies...
pip install pywebview pystray pillow win10toast pyinstaller --quiet
if %errorlevel% neq 0 (
    echo ERROR: pip install failed. Make sure Python is installed.
    pause
    exit /b 1
)

echo [3/5] Installing frontend dependencies...
call npm --prefix system-ui ci
if %errorlevel% neq 0 (
    echo ERROR: npm install failed. Make sure Node.js is installed.
    pause
    exit /b 1
)

echo [4/5] Building and verifying the frontend...
call npm --prefix system-ui run build
if %errorlevel% neq 0 (
    echo ERROR: frontend build failed.
    pause
    exit /b 1
)

echo [5/5] Building CVIS.exe...
python -m PyInstaller build_app.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo ERROR: PyInstaller build failed. Check output above.
    pause
    exit /b 1
)

echo Done!
echo.
echo Output: dist\CVIS.exe
echo Double-click dist\CVIS.exe to launch.
echo.
pause
