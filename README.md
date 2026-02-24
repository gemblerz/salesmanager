# Sales Manager

A simple, user-friendly web application for managing merchandise inventory and tracking sales. Designed with a clean, large-font interface suitable for all users.

## Features

- **Merchandise Management**: Add, view, and delete merchandise items
- **Consumer Management**: Add, view, and delete consumers (name, phone, address, notes)
- **Inventory Tracking**: Monitor stock quantities in real-time
- **Sales Recording**: Record sales transactions with both product and consumer selection
- **Sales History**: View complete sales history with period filters and consumer information
- **Statistics Dashboard**: Track total items, stock, sales, and revenue
- **Database Backup**: All data is stored in a SQLite database (salesmanager.db)

## Requirements

- Python 3.7 or higher
- Modern web browser (Chrome, Firefox, Edge, Safari)

## Installation & Running

### Windows

1. Double-click `run.bat`
2. The script will:
   - Create a virtual environment
   - Install required dependencies
   - Start the application
3. Open your browser to http://127.0.0.1:5000

### Linux / Mac

1. Open terminal in the project directory
2. Run: `./run.sh`
3. The script will:
   - Create a virtual environment
   - Install required dependencies
   - Start the application
4. Open your browser to http://127.0.0.1:5000

### Manual Installation

If the automatic scripts don't work, you can run manually:

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
gunicorn --bind 127.0.0.1:5000 app:app
```

### Debug Mode

By default, the application runs in production mode using Gunicorn.

## Usage

### Adding Merchandise

1. Go to the "Merchandise" tab (default view)
2. Fill in the form:
   - Item Name (required)
   - Description (optional)
   - Quantity (required)
   - Price per Unit (required)
3. Click "Add Merchandise"

### Recording a Sale

1. Click the "Record Sale" tab
2. Select an item from the dropdown (shows stock, price, and ID to disambiguate duplicate names)
3. Select the consumer
4. Enter the quantity sold
5. Click "Record Sale"
6. The inventory will automatically update

### Viewing Sales History

1. Click the "Sales History" tab
2. View all past sales with:
    - Date and time
    - Item name
    - Consumer name
    - Quantity sold
    - Unit price
    - Total price

## Database

All data is stored in `salesmanager.db` in the project directory. This file is automatically created on first run.

**Backup**: To backup your data, simply copy the `salesmanager.db` file to a safe location.

**Restore**: To restore, replace the `salesmanager.db` file with your backup.

## Interface Design

The interface features:
- Large, readable fonts (18-36px)
- High-contrast colors
- Clear, prominent buttons
- Simple navigation with tabs
- Visual feedback for all actions

## Stopping the Application

Press `Ctrl+C` in the terminal/command prompt where the application is running.

## Troubleshooting

**Port already in use**: If port 5000 is already in use, run Gunicorn with a different port:
```bash
gunicorn --bind 127.0.0.1:5001 app:app
```

**Database locked error**: Close any other instances of the application that might be accessing the database.

## License

This project is open source and available for personal and commercial use.
