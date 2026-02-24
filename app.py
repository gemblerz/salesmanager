"""
Sales Manager - A simple merchandise management system
"""
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, g

app = Flask(__name__)
DATABASE = 'salesmanager.db'


def get_db():
    """Get database connection"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    """Close database connection"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize the database"""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Create merchandise table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS merchandise (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                quantity INTEGER NOT NULL DEFAULT 0,
                price REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create sales table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchandise_id INTEGER NOT NULL,
                quantity_sold INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                total_price REAL NOT NULL,
                sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (merchandise_id) REFERENCES merchandise (id)
            )
        ''')
        
        db.commit()


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/api/merchandise', methods=['GET'])
def get_merchandise():
    """Get all merchandise"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM merchandise ORDER BY name')
    items = [dict(row) for row in cursor.fetchall()]
    return jsonify(items)


@app.route('/api/merchandise', methods=['POST'])
def add_merchandise():
    """Add new merchandise"""
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        INSERT INTO merchandise (name, description, quantity, price)
        VALUES (?, ?, ?, ?)
    ''', (data['name'], data.get('description', ''), data['quantity'], data['price']))
    
    db.commit()
    return jsonify({'id': cursor.lastrowid, 'message': '상품이 성공적으로 등록되었습니다'})


@app.route('/api/merchandise/<int:merchandise_id>', methods=['PUT'])
def update_merchandise(merchandise_id):
    """Update merchandise"""
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''
        UPDATE merchandise 
        SET name = ?, description = ?, quantity = ?, price = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (data['name'], data.get('description', ''), data['quantity'], data['price'], merchandise_id))
    
    db.commit()
    return jsonify({'message': '상품 정보가 업데이트되었습니다'})


@app.route('/api/merchandise/<int:merchandise_id>', methods=['DELETE'])
def delete_merchandise(merchandise_id):
    """Delete merchandise"""
    db = get_db()
    cursor = db.cursor()
    
    # Check if merchandise has sales records
    cursor.execute('SELECT COUNT(*) as count FROM sales WHERE merchandise_id = ?', (merchandise_id,))
    sales_count = cursor.fetchone()['count']
    
    if sales_count > 0:
        return jsonify({'error': '판매 이력이 있는 상품은 삭제할 수 없습니다'}), 400
    
    cursor.execute('DELETE FROM merchandise WHERE id = ?', (merchandise_id,))
    db.commit()
    return jsonify({'message': '상품이 삭제되었습니다'})


@app.route('/api/sales', methods=['POST'])
def record_sale():
    """Record a sale"""
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    # Get current quantity
    cursor.execute('SELECT quantity, price FROM merchandise WHERE id = ?', (data['merchandise_id'],))
    row = cursor.fetchone()
    
    if not row:
        return jsonify({'error': '상품을 찾을 수 없습니다'}), 404
    
    current_quantity = row['quantity']
    price = row['price']
    quantity_sold = data['quantity_sold']
    
    if current_quantity < quantity_sold:
        return jsonify({'error': '재고가 부족합니다'}), 400
    
    # Record sale
    total_price = price * quantity_sold
    cursor.execute('''
        INSERT INTO sales (merchandise_id, quantity_sold, unit_price, total_price)
        VALUES (?, ?, ?, ?)
    ''', (data['merchandise_id'], quantity_sold, price, total_price))
    
    # Update merchandise quantity
    cursor.execute('''
        UPDATE merchandise 
        SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (quantity_sold, data['merchandise_id']))
    
    db.commit()
    return jsonify({'message': '판매가 기록되었습니다', 'total_price': total_price})


@app.route('/api/sales', methods=['GET'])
def get_sales():
    """Get sales history"""
    db = get_db()
    cursor = db.cursor()
    period = request.args.get('period', 'all')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = '''
        SELECT s.*, m.name as merchandise_name
        FROM sales s
        JOIN merchandise m ON s.merchandise_id = m.id
    '''
    conditions = []
    params = []

    if start_date or end_date:
        try:
            if start_date:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                conditions.append('s.sale_date >= ?')
                params.append(start.strftime('%Y-%m-%d 00:00:00'))
            if end_date:
                end = datetime.strptime(end_date, '%Y-%m-%d')
                conditions.append('s.sale_date <= ?')
                params.append(end.strftime('%Y-%m-%d 23:59:59'))
        except ValueError:
            return jsonify({'error': '잘못된 날짜 형식입니다. YYYY-MM-DD 형식을 사용하세요.'}), 400
    elif period == 'last_month':
        first_day_this_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day_last_month = first_day_this_month - timedelta(seconds=1)
        first_day_last_month = last_day_last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        conditions.append('s.sale_date >= ? AND s.sale_date <= ?')
        params.extend([
            first_day_last_month.strftime('%Y-%m-%d %H:%M:%S'),
            last_day_last_month.strftime('%Y-%m-%d %H:%M:%S')
        ])
    elif period == 'this_month':
        first_day_this_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        conditions.append('s.sale_date >= ?')
        params.append(first_day_this_month.strftime('%Y-%m-%d %H:%M:%S'))
    elif period == 'last_30_days':
        thirty_days_ago = datetime.now() - timedelta(days=30)
        conditions.append('s.sale_date >= ?')
        params.append(thirty_days_ago.strftime('%Y-%m-%d %H:%M:%S'))

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' ORDER BY s.sale_date DESC'
    cursor.execute(query, params)
    sales = [dict(row) for row in cursor.fetchall()]
    return jsonify(sales)


if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=False)
