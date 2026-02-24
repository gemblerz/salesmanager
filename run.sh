#!/bin/bash

# Sales Manager - Linux/Mac Run Script

echo "========================================"
echo "  Sales Manager - Setup and Run"
echo "========================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null
then
    echo "Error: Python 3 is not installed."
    echo "Please install Python 3 from https://www.python.org/"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Run the application
echo ""
echo "========================================"
echo "  Starting Sales Manager..."
echo "========================================"
echo ""
echo "The application will be available at:"
echo "  http://127.0.0.1:5000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

gunicorn --bind 127.0.0.1:5000 app:app
