@echo off
echo =======================================================
echo     🎨 Starting POD Automation Pilot Dashboard...
echo =======================================================
echo.

:: Add the src directory to PYTHONPATH so imports work correctly
set PYTHONPATH=%PYTHONPATH%;%cd%\outputs\src

:: Launch the Flask application
python outputs\web_interface\app.py

echo.
pause
