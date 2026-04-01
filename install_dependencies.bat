@echo off
echo =======================================================
echo     📦 Installing POD Automation Pilot Dependencies...
echo =======================================================
echo.

echo [1/2] Installing Python packages...
pip install -r requirements.txt
echo.

echo [2/2] Installing Playwright Chromium browser...
echo (This is required for the Botasaurus framework to bypass Cloudflare)
playwright install chromium
echo.

echo ✅ Installation complete! You can now run launch_app.bat
echo.
pause
