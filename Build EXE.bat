@echo off
rem One-time build of the standalone Windows app.
rem Produces:  dist\Relay Optimiser.exe  (double-clickable, no Python needed)
cd /d "%~dp0"

echo Installing/updating build tools...
python -m pip install --upgrade pyinstaller pulp openpyxl
if errorlevel 1 goto :error

echo.
echo Building the app (this can take a minute)...
python -m PyInstaller --noconfirm "RelayOptimiser.spec"
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  Done!  Your app is here:
echo     dist\Relay Optimiser.exe
echo  You can copy that single file anywhere and double-click it.
echo ============================================================
pause
exit /b 0

:error
echo.
echo Build failed -- see the messages above.
pause
exit /b 1
