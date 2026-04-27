"""
Sales Manager - A simple merchandise management system
"""
import os
import sqlite3
import calendar
import hmac
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Flask, render_template, request, jsonify, g, send_file, session

app = Flask(__name__)
DATABASE = os.environ.get('DATABASE_PATH', 'database/salesmanager.db')
SITE_PASSWORD = os.environ.get('SITE_PASSWORD', 'salesmanager')
DEPLOYMENT_TYPE = os.environ.get('DEPLOYMENT_TYPE', 'local').strip().lower()
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or f'{SITE_PASSWORD}-salesmanager-session'


def is_site_password_required():
    """Whether site password authentication is required for this deployment."""
    return DEPLOYMENT_TYPE == 'public'


def subtract_months(reference_time, months):
    """Return datetime shifted back by calendar months, preserving time."""
    year = reference_time.year
    month = reference_time.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(reference_time.day, calendar.monthrange(year, month)[1])
    return reference_time.replace(year=year, month=month, day=day)


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
        
        # Create consumers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS consumers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                address TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create sales table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchandise_id INTEGER NOT NULL,
                consumer_id INTEGER,
                quantity_sold INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                total_price REAL NOT NULL,
                sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (merchandise_id) REFERENCES merchandise (id),
                FOREIGN KEY (consumer_id) REFERENCES consumers (id)
            )
        ''')

        # Create app configuration table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Backward-compatible migrations for older DBs
        cursor.execute('PRAGMA table_info(sales)')
        sales_columns = [row['name'] for row in cursor.fetchall()]
        if 'consumer_id' not in sales_columns:
            cursor.execute('ALTER TABLE sales ADD COLUMN consumer_id INTEGER')

        cursor.execute('PRAGMA table_info(consumers)')
        consumer_columns = [row['name'] for row in cursor.fetchall()]
        if 'phone' not in consumer_columns:
            cursor.execute('ALTER TABLE consumers ADD COLUMN phone TEXT')
        if 'address' not in consumer_columns:
            cursor.execute('ALTER TABLE consumers ADD COLUMN address TEXT')
        if 'notes' not in consumer_columns:
            cursor.execute('ALTER TABLE consumers ADD COLUMN notes TEXT')
        if 'created_at' not in consumer_columns:
            cursor.execute('ALTER TABLE consumers ADD COLUMN created_at TIMESTAMP')
        if 'updated_at' not in consumer_columns:
            cursor.execute('ALTER TABLE consumers ADD COLUMN updated_at TIMESTAMP')

        # Ensure timezone configuration default exists
        cursor.execute('''
            INSERT OR IGNORE INTO app_config (key, value)
            VALUES ('timezone', 'Asia/Seoul')
        ''')
        
        db.commit()


@app.before_request
def ensure_db_ready():
    """Ensure required DB tables exist before handling requests"""
    if not app.config.get('TESTING'):
        if request.endpoint == 'static':
            return

        if request.endpoint in ('index', 'authenticate'):
            return

        if is_site_password_required() and not session.get('authenticated'):
            return jsonify({'error': '비밀번호 인증이 필요합니다'}), 401

    if not app.config.get('_DB_INITIALIZED', False):
        init_db()
        app.config['_DB_INITIALIZED'] = True


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html', site_password_required=is_site_password_required())


@app.route('/api/authenticate', methods=['POST'])
def authenticate():
    """Authenticate website access"""
    if not is_site_password_required():
        return jsonify({'message': '인증이 필요하지 않은 배포 모드입니다'})

    data = request.json or {}
    password = data.get('password', '')
    if not isinstance(password, str):
        return jsonify({'error': '비밀번호 형식이 올바르지 않습니다'}), 400
    if not hmac.compare_digest(password, SITE_PASSWORD):
        return jsonify({'error': '비밀번호가 올바르지 않습니다'}), 401

    session['authenticated'] = True
    return jsonify({'message': '인증되었습니다'})


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
    
    quantity = data.get('quantity')
    if quantity in (None, ''):
        quantity = 0
    if not isinstance(quantity, int) or quantity < 0:
        return jsonify({'error': '재고 수량은 0 이상의 정수여야 합니다'}), 400

    cursor.execute('''
        INSERT INTO merchandise (name, description, quantity, price)
        VALUES (?, ?, ?, ?)
    ''', (data['name'], data.get('description', ''), quantity, data['price']))
    
    db.commit()
    return jsonify({'id': cursor.lastrowid, 'message': '상품이 성공적으로 등록되었습니다'})


@app.route('/api/merchandise/<int:merchandise_id>', methods=['PUT'])
def update_merchandise(merchandise_id):
    """Update merchandise"""
    data = request.json
    db = get_db()
    cursor = db.cursor()
    
    quantity = data.get('quantity')
    if quantity in (None, ''):
        quantity = 0
    if not isinstance(quantity, int) or quantity < 0:
        return jsonify({'error': '재고 수량은 0 이상의 정수여야 합니다'}), 400

    cursor.execute('''
        UPDATE merchandise 
        SET name = ?, description = ?, quantity = ?, price = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (data['name'], data.get('description', ''), quantity, data['price'], merchandise_id))
    
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
    
    cursor.execute('SELECT price FROM merchandise WHERE id = ?', (data['merchandise_id'],))
    row = cursor.fetchone()
    
    if not row:
        return jsonify({'error': '상품을 찾을 수 없습니다'}), 404
    
    price = row['price']
    quantity_sold = data.get('quantity_sold', 1)
    if not isinstance(quantity_sold, int) or quantity_sold <= 0:
        return jsonify({'error': '판매 수량은 1 이상이어야 합니다'}), 400

    total_price_input = data.get('total_price')
    if total_price_input is not None:
        if not isinstance(total_price_input, (int, float)) or total_price_input <= 0:
            return jsonify({'error': '판매금은 0보다 커야 합니다'}), 400
        total_price = float(total_price_input)
        unit_price = total_price / quantity_sold
    else:
        unit_price = data.get('unit_price', price)
        if not isinstance(unit_price, (int, float)) or unit_price <= 0:
            return jsonify({'error': '단가는 0보다 커야 합니다'}), 400
        total_price = unit_price * quantity_sold
    consumer_id = data.get('consumer_id')
    if consumer_id is None:
        return jsonify({'error': '소비자를 선택해주세요'}), 400

    cursor.execute('SELECT id FROM consumers WHERE id = ?', (consumer_id,))
    if not cursor.fetchone():
        return jsonify({'error': '소비자를 찾을 수 없습니다'}), 404
    
    # Record sale
    cursor.execute('''
        INSERT INTO sales (merchandise_id, consumer_id, quantity_sold, unit_price, total_price)
        VALUES (?, ?, ?, ?, ?)
    ''', (data['merchandise_id'], consumer_id, quantity_sold, unit_price, total_price))
    
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
    limit = request.args.get('limit')
    offset = request.args.get('offset', '0')

    query = '''
        SELECT s.*, m.name as merchandise_name, m.description as merchandise_description,
               c.name as consumer_name, c.phone as consumer_phone, c.address as consumer_address
        FROM sales s
        JOIN merchandise m ON s.merchandise_id = m.id
        LEFT JOIN consumers c ON s.consumer_id = c.id
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
    elif period == 'last_3_months':
        three_months_ago = subtract_months(datetime.now(), 3)
        conditions.append('s.sale_date >= ?')
        params.append(three_months_ago.strftime('%Y-%m-%d %H:%M:%S'))
    elif period == 'last_6_months':
        six_months_ago = subtract_months(datetime.now(), 6)
        conditions.append('s.sale_date >= ?')
        params.append(six_months_ago.strftime('%Y-%m-%d %H:%M:%S'))
    elif period == 'this_year':
        first_day_this_year = datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        conditions.append('s.sale_date >= ?')
        params.append(first_day_this_year.strftime('%Y-%m-%d %H:%M:%S'))

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' ORDER BY s.sale_date DESC'

    if limit is not None:
        try:
            limit_value = int(limit)
            offset_value = int(offset)
        except ValueError:
            return jsonify({'error': 'limit과 offset은 정수여야 합니다'}), 400
        if limit_value not in (20, 50, 100):
            return jsonify({'error': 'limit은 20, 50, 100 중 하나여야 합니다'}), 400
        if offset_value < 0:
            return jsonify({'error': 'offset은 0 이상이어야 합니다'}), 400

        count_query = 'SELECT COUNT(*) as total FROM sales s'
        if conditions:
            count_query += ' WHERE ' + ' AND '.join(conditions)
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()['total']

        paginated_query = query + ' LIMIT ? OFFSET ?'
        cursor.execute(paginated_query, params + [limit_value, offset_value])
        sales = [dict(row) for row in cursor.fetchall()]
        return jsonify({
            'sales': sales,
            'total': total_count,
            'limit': limit_value,
            'offset': offset_value
        })

    cursor.execute(query, params)
    sales = [dict(row) for row in cursor.fetchall()]
    return jsonify(sales)


@app.route('/api/sales/<int:sale_id>', methods=['PUT'])
def update_sale(sale_id):
    """Update a sale record"""
    data = request.json
    db = get_db()
    cursor = db.cursor()

    quantity_sold = data.get('quantity_sold')
    consumer_id = data.get('consumer_id')
    unit_price = data.get('unit_price')
    total_price_input = data.get('total_price')
    if not isinstance(quantity_sold, int) or quantity_sold <= 0:
        return jsonify({'error': '판매 수량은 1 이상이어야 합니다'}), 400
    if consumer_id is None:
        return jsonify({'error': '소비자를 선택해주세요'}), 400

    cursor.execute('SELECT id FROM consumers WHERE id = ?', (consumer_id,))
    if not cursor.fetchone():
        return jsonify({'error': '소비자를 찾을 수 없습니다'}), 404

    cursor.execute('SELECT merchandise_id, quantity_sold, unit_price FROM sales WHERE id = ?', (sale_id,))
    sale = cursor.fetchone()
    if not sale:
        return jsonify({'error': '판매 기록을 찾을 수 없습니다'}), 404

    if total_price_input is not None:
        if not isinstance(total_price_input, (int, float)) or total_price_input <= 0:
            return jsonify({'error': '판매금은 0보다 커야 합니다'}), 400
        total_price = float(total_price_input)
        unit_price = total_price / quantity_sold
    else:
        if unit_price is None:
            unit_price = sale['unit_price']
        if not isinstance(unit_price, (int, float)) or unit_price <= 0:
            return jsonify({'error': '단가는 0보다 커야 합니다'}), 400
        total_price = unit_price * quantity_sold
    cursor.execute('''
        UPDATE sales
        SET consumer_id = ?, quantity_sold = ?, unit_price = ?, total_price = ?
        WHERE id = ?
    ''', (consumer_id, quantity_sold, unit_price, total_price, sale_id))

    db.commit()
    return jsonify({'message': '판매 기록이 수정되었습니다', 'total_price': total_price})


@app.route('/api/sales/<int:sale_id>', methods=['DELETE'])
def delete_sale(sale_id):
    """Delete a sale record and restore inventory"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT merchandise_id, quantity_sold FROM sales WHERE id = ?', (sale_id,))
    sale = cursor.fetchone()
    if not sale:
        return jsonify({'error': '판매 기록을 찾을 수 없습니다'}), 404

    cursor.execute('DELETE FROM sales WHERE id = ?', (sale_id,))
    db.commit()
    return jsonify({'message': '판매 기록이 삭제되었습니다'})


@app.route('/api/consumers', methods=['GET'])
def get_consumers():
    """Get all consumers"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT id, name, phone, address, notes, created_at, updated_at
        FROM consumers
        ORDER BY name, id
    ''')
    consumers = [dict(row) for row in cursor.fetchall()]
    return jsonify(consumers)


@app.route('/api/consumers', methods=['POST'])
def add_consumer():
    """Add new consumer"""
    data = request.json
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        INSERT INTO consumers (name, phone, address, notes)
        VALUES (?, ?, ?, ?)
    ''', (data['name'], data.get('phone', ''), data.get('address', ''), data.get('notes', '')))
    db.commit()
    return jsonify({'id': cursor.lastrowid, 'message': '소비자가 성공적으로 등록되었습니다'})


@app.route('/api/consumers/<int:consumer_id>', methods=['PUT'])
def update_consumer(consumer_id):
    """Update consumer"""
    data = request.json
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        UPDATE consumers
        SET name = ?, phone = ?, address = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (data['name'], data.get('phone', ''), data.get('address', ''), data.get('notes', ''), consumer_id))
    if cursor.rowcount == 0:
        return jsonify({'error': '소비자를 찾을 수 없습니다'}), 404
    db.commit()
    return jsonify({'message': '소비자 정보가 업데이트되었습니다'})


@app.route('/api/consumers/<int:consumer_id>', methods=['DELETE'])
def delete_consumer(consumer_id):
    """Delete consumer"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM sales WHERE consumer_id = ?', (consumer_id,))
    sales_count = cursor.fetchone()['count']
    if sales_count > 0:
        return jsonify({'error': '판매 이력이 있는 소비자는 삭제할 수 없습니다'}), 400
    cursor.execute('DELETE FROM consumers WHERE id = ?', (consumer_id,))
    db.commit()
    return jsonify({'message': '소비자가 삭제되었습니다'})


@app.route('/api/config/backup', methods=['GET'])
def backup_database():
    """Download the current database file"""
    backup_format = request.args.get('format', 'db').lower()
    if not os.path.exists(DATABASE):
        init_db()

    if backup_format != 'db':
        return jsonify({'error': '지원하지 않는 백업 형식입니다'}), 400

    with open(DATABASE, 'rb') as db_file:
        db_content = db_file.read()
    return send_file(BytesIO(db_content), as_attachment=True, download_name='salesmanager-backup.db')


@app.route('/api/config/restore', methods=['POST'])
def restore_database():
    """Restore database from uploaded file"""
    upload = request.files.get('database')
    if not upload or upload.filename == '':
        return jsonify({'error': '복원할 데이터베이스 파일을 선택해주세요'}), 400
    filename = upload.filename.lower()
    if not filename.endswith(('.db', '.sqlite', '.sqlite3')):
        return jsonify({'error': '지원하지 않는 복원 파일 형식입니다'}), 400

    db_connection = getattr(g, '_database', None)
    if db_connection is not None:
        db_connection.close()
        g._database = None

    upload.save(DATABASE)

    app.config['_DB_INITIALIZED'] = False
    init_db()
    app.config['_DB_INITIALIZED'] = True
    return jsonify({'message': '데이터베이스를 복원했습니다'})


@app.route('/api/config/timezone', methods=['GET'])
def get_timezone_config():
    """Get current timezone configuration"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT value FROM app_config WHERE key = ?', ('timezone',))
    row = cursor.fetchone()
    timezone = row['value'] if row else 'Asia/Seoul'
    return jsonify({'timezone': timezone})


@app.route('/api/config/timezone', methods=['POST'])
def update_timezone_config():
    """Update timezone configuration"""
    data = request.json or {}
    timezone = data.get('timezone', '').strip()
    if not timezone:
        return jsonify({'error': '시간대를 입력해주세요'}), 400

    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return jsonify({'error': '유효하지 않은 시간대입니다'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        INSERT INTO app_config (key, value, updated_at)
        VALUES ('timezone', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
    ''', (timezone,))
    db.commit()
    return jsonify({'message': '시간대 설정이 저장되었습니다', 'timezone': timezone})


if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=False)
