@echo off
echo ============================================================
echo   CVIS Desktop App Builder
echo ============================================================
echo.

:: Install required packages
echo [1/3] Installing build dependencies...
pip install pywebview pystray pillow win10toast pyinstaller --quiet
if %errorlevel% neq 0 (
    echo ERROR: pip install failed. Make sure Python is installed.
    pause
    exit /b 1
)

echo [2/3] Building CVIS.exe...
python -m PyInstaller build_app.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo ERROR: PyInstaller build failed. Check output above.
    pause
    exit /b 1
)

echo [3/3] Done!
echo.
echo Output: dist\CVIS.exe
echo Double-click dist\CVIS.exe to launch.
echo.
pause
