@echo off
REM Launcher for Windows. Arguments are passed through, e.g. run.bat --low
cd /d "%~dp0"
where py >nul 2>nul && (py -3 main.py %* & goto :eof)
where python >nul 2>nul && (python main.py %* & goto :eof)
echo Python 3 was not found. Install it from https://www.python.org/downloads/
pause
