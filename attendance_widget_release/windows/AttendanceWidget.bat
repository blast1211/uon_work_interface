@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONW=%ROOT%app\.venv\Scripts\pythonw.exe"
set "PYTHON=%ROOT%app\.venv\Scripts\python.exe"
set "APP_MAIN=%ROOT%app\main.py"

if exist "%PYTHONW%" (
    start "" "%PYTHONW%" "%APP_MAIN%"
    exit /b 0
)

if exist "%PYTHON%" (
    start "Attendance Widget" "%PYTHON%" "%APP_MAIN%"
    exit /b 0
)

echo Python runtime was not found in app\.venv\Scripts.
pause
exit /b 1
