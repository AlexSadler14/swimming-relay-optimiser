@echo off
rem Double-click launcher for the Swimming Relay Optimiser.
rem Opens the interactive editor window. You can pick a swimmers file from the
rem window itself, or drag a CSV/XLSX onto this .bat to open it directly.
cd /d "%~dp0"
python main.py %*
if errorlevel 1 (
    echo.
    echo The program exited with an error. See the message above.
    pause
)
