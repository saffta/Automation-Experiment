@echo off
echo =======================================================
echo     🎨 Starting POD Automation Pilot Dashboard...
echo =======================================================
echo.

:: Add the src directory to PYTHONPATH so imports work correctly
set PYTHONPATH=%PYTHONPATH%;%cd%\outputs\src

:: Force kill any zombie processes holding port 5001 from a previous run
echo 🧹 Cleaning up old connections...
for /f "tokens=5" %%a in ('netstat -ano ^| find ":5001 "') do taskkill /F /PID %%a >nul 2>&1

:: Launch the Flask application
python outputs\web_interface\app.py

echo.
pause
