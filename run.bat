@echo off
REM Sales Manager - Windows Run Script

echo ========================================
echo   Sales Manager - Setup and Run
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed.
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM Run the application
echo.
echo ========================================
echo   Starting Sales Manager...
echo ========================================
echo.
echo The application will be available at:
echo   http://127.0.0.1:5000
echo.
echo Press Ctrl+C to stop the server
echo.

where gunicorn >nul 2>&1
if errorlevel 1 (
    echo Gunicorn is not available on this environment. Falling back to python app.py
    python app.py
    goto :end
)

gunicorn --bind 127.0.0.1:5000 app:app
:end

pause
