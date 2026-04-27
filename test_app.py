import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import app as salesmanager
import run


class SalesManagerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, 'test.db')
        salesmanager.DATABASE = self.db_path
        salesmanager.app.config['TESTING'] = True

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute('''
                CREATE TABLE consumers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE TABLE merchandise (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    price REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    merchandise_id INTEGER NOT NULL,
                    quantity_sold INTEGER NOT NULL,
                    unit_price REAL NOT NULL,
                    total_price REAL NOT NULL,
                    sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            db.commit()

        salesmanager.init_db()
        self.client = salesmanager.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_consumers_with_legacy_schema(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            db.execute('INSERT INTO consumers (name) VALUES (?)', ('홍길동',))
            db.commit()

        response = self.client.get('/api/consumers')
        self.assertEqual(response.status_code, 200)
        consumers = response.get_json()
        self.assertEqual(consumers[0]['name'], '홍길동')
        self.assertIn('notes', consumers[0])

    def test_update_merchandise(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO merchandise (name, description, quantity, price) VALUES (?, ?, ?, ?)',
                ('원래상품', '원래설명', 3, 100.0)
            )
            merchandise_id = cursor.lastrowid
            db.commit()

        response = self.client.put(
            f'/api/merchandise/{merchandise_id}',
            json={'name': '수정상품', 'description': '수정설명', 'quantity': 7, 'price': 150.0}
        )
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            merchandise = db.execute(
                'SELECT name, description, quantity, price FROM merchandise WHERE id = ?',
                (merchandise_id,)
            ).fetchone()

        self.assertEqual(merchandise['name'], '수정상품')
        self.assertEqual(merchandise['description'], '수정설명')
        self.assertEqual(merchandise['quantity'], 7)
        self.assertEqual(merchandise['price'], 150.0)

    def test_update_consumer(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO consumers (name, phone, address, notes) VALUES (?, ?, ?, ?)',
                ('원래이름', '010-1111-1111', '원래주소', '원래메모')
            )
            consumer_id = cursor.lastrowid
            db.commit()

        response = self.client.put(
            f'/api/consumers/{consumer_id}',
            json={
                'name': '수정이름',
                'phone': '010-2222-2222',
                'address': '수정주소',
                'notes': '수정메모'
            }
        )
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            consumer = db.execute(
                'SELECT name, phone, address, notes FROM consumers WHERE id = ?',
                (consumer_id,)
            ).fetchone()

        self.assertEqual(consumer['name'], '수정이름')
        self.assertEqual(consumer['phone'], '010-2222-2222')
        self.assertEqual(consumer['address'], '수정주소')
        self.assertEqual(consumer['notes'], '수정메모')

    def test_update_consumer_not_found(self):
        response = self.client.put(
            '/api/consumers/9999',
            json={'name': '없는사용자', 'phone': '', 'address': '', 'notes': ''}
        )
        self.assertEqual(response.status_code, 404)

    def test_update_sale_updates_inventory_and_total(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO merchandise (name, description, quantity, price) VALUES (?, ?, ?, ?)',
                ('테스트상품', '설명', 8, 100.0)
            )
            merchandise_id = cursor.lastrowid
            cursor.execute('INSERT INTO consumers (name) VALUES (?)', ('소비자1',))
            consumer_id_1 = cursor.lastrowid
            cursor.execute('INSERT INTO consumers (name) VALUES (?)', ('소비자2',))
            consumer_id_2 = cursor.lastrowid
            cursor.execute(
                'INSERT INTO sales (merchandise_id, consumer_id, quantity_sold, unit_price, total_price) VALUES (?, ?, ?, ?, ?)',
                (merchandise_id, consumer_id_1, 2, 100.0, 200.0)
            )
            sale_id = cursor.lastrowid
            db.commit()

        response = self.client.put(
            f'/api/sales/{sale_id}',
            json={'quantity_sold': 5, 'consumer_id': consumer_id_2}
        )
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            merchandise = db.execute(
                'SELECT quantity FROM merchandise WHERE id = ?',
                (merchandise_id,)
            ).fetchone()
            sale = db.execute(
                'SELECT quantity_sold, consumer_id, total_price FROM sales WHERE id = ?',
                (sale_id,)
            ).fetchone()

        self.assertEqual(merchandise['quantity'], 8)
        self.assertEqual(sale['quantity_sold'], 5)
        self.assertEqual(sale['consumer_id'], consumer_id_2)
        self.assertEqual(sale['total_price'], 500.0)

    def test_add_merchandise_allows_missing_quantity(self):
        response = self.client.post(
            '/api/merchandise',
            json={'name': '수량옵션상품', 'description': '설명', 'price': 900.0}
        )
        self.assertEqual(response.status_code, 200)
        merchandise_id = response.get_json()['id']

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            merchandise = db.execute(
                'SELECT quantity FROM merchandise WHERE id = ?',
                (merchandise_id,)
            ).fetchone()
        self.assertEqual(merchandise['quantity'], 0)

    def test_record_sale_allows_missing_quantity(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO merchandise (name, description, quantity, price) VALUES (?, ?, ?, ?)',
                ('기본수량판매상품', '설명', 0, 500.0)
            )
            merchandise_id = cursor.lastrowid
            cursor.execute('INSERT INTO consumers (name) VALUES (?)', ('기본수량소비자',))
            consumer_id = cursor.lastrowid
            db.commit()

        response = self.client.post(
            '/api/sales',
            json={'merchandise_id': merchandise_id, 'consumer_id': consumer_id}
        )
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            sale = db.execute(
                'SELECT quantity_sold, total_price FROM sales WHERE merchandise_id = ?',
                (merchandise_id,)
            ).fetchone()
        self.assertEqual(sale['quantity_sold'], 1)
        self.assertEqual(sale['total_price'], 500.0)

    def test_record_sale_supports_manual_unit_price(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO merchandise (name, description, quantity, price) VALUES (?, ?, ?, ?)',
                ('수동단가상품', '설명', 10, 100.0)
            )
            merchandise_id = cursor.lastrowid
            cursor.execute('INSERT INTO consumers (name) VALUES (?)', ('소비자',))
            consumer_id = cursor.lastrowid
            db.commit()

        response = self.client.post(
            '/api/sales',
            json={'merchandise_id': merchandise_id, 'consumer_id': consumer_id, 'quantity_sold': 2, 'unit_price': 120.0}
        )
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            sale = db.execute(
                'SELECT unit_price, total_price FROM sales WHERE merchandise_id = ?',
                (merchandise_id,)
            ).fetchone()
        self.assertEqual(sale['unit_price'], 120.0)
        self.assertEqual(sale['total_price'], 240.0)

    def test_update_sale_supports_manual_unit_price(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO merchandise (name, description, quantity, price) VALUES (?, ?, ?, ?)',
                ('수정단가상품', '설명', 8, 100.0)
            )
            merchandise_id = cursor.lastrowid
            cursor.execute('INSERT INTO consumers (name) VALUES (?)', ('소비자1',))
            consumer_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO sales (merchandise_id, consumer_id, quantity_sold, unit_price, total_price) VALUES (?, ?, ?, ?, ?)',
                (merchandise_id, consumer_id, 2, 100.0, 200.0)
            )
            sale_id = cursor.lastrowid
            db.commit()

        response = self.client.put(
            f'/api/sales/{sale_id}',
            json={'quantity_sold': 3, 'consumer_id': consumer_id, 'unit_price': 110.0}
        )
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            sale = db.execute(
                'SELECT unit_price, total_price FROM sales WHERE id = ?',
                (sale_id,)
            ).fetchone()
        self.assertEqual(sale['unit_price'], 110.0)
        self.assertEqual(sale['total_price'], 330.0)

    def test_record_sale_supports_manual_total_price(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO merchandise (name, description, quantity, price) VALUES (?, ?, ?, ?)',
                ('총액입력상품', '설명', 10, 100.0)
            )
            merchandise_id = cursor.lastrowid
            cursor.execute('INSERT INTO consumers (name) VALUES (?)', ('총액소비자',))
            consumer_id = cursor.lastrowid
            db.commit()

        response = self.client.post(
            '/api/sales',
            json={'merchandise_id': merchandise_id, 'consumer_id': consumer_id, 'quantity_sold': 2, 'total_price': 250.0}
        )
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            sale = db.execute(
                'SELECT unit_price, total_price FROM sales WHERE merchandise_id = ?',
                (merchandise_id,)
            ).fetchone()
        self.assertEqual(sale['unit_price'], 125.0)
        self.assertEqual(sale['total_price'], 250.0)

    def test_update_sale_supports_manual_total_price(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO merchandise (name, description, quantity, price) VALUES (?, ?, ?, ?)',
                ('총액수정상품', '설명', 8, 100.0)
            )
            merchandise_id = cursor.lastrowid
            cursor.execute('INSERT INTO consumers (name) VALUES (?)', ('소비자1',))
            consumer_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO sales (merchandise_id, consumer_id, quantity_sold, unit_price, total_price) VALUES (?, ?, ?, ?, ?)',
                (merchandise_id, consumer_id, 2, 100.0, 200.0)
            )
            sale_id = cursor.lastrowid
            db.commit()

        response = self.client.put(
            f'/api/sales/{sale_id}',
            json={'quantity_sold': 5, 'consumer_id': consumer_id, 'total_price': 400.0}
        )
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            sale = db.execute(
                'SELECT unit_price, total_price FROM sales WHERE id = ?',
                (sale_id,)
            ).fetchone()
        self.assertEqual(sale['unit_price'], 80.0)
        self.assertEqual(sale['total_price'], 400.0)

    def test_get_sales_supports_extended_period_filters(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO merchandise (name, description, quantity, price) VALUES (?, ?, ?, ?)',
                ('기간상품', '설명', 10, 100.0)
            )
            merchandise_id = cursor.lastrowid
            cursor.execute('INSERT INTO consumers (name) VALUES (?)', ('기간소비자',))
            consumer_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO sales (merchandise_id, consumer_id, quantity_sold, unit_price, total_price) VALUES (?, ?, ?, ?, ?)',
                (merchandise_id, consumer_id, 1, 100.0, 100.0)
            )
            db.commit()

        for period in ('last_3_months', 'last_6_months', 'this_year'):
            response = self.client.get(f'/api/sales?period={period}')
            self.assertEqual(response.status_code, 200)

    def test_get_sales_supports_pagination(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO merchandise (name, description, quantity, price) VALUES (?, ?, ?, ?)',
                ('페이징상품', '설명', 100, 100.0)
            )
            merchandise_id = cursor.lastrowid
            cursor.execute('INSERT INTO consumers (name) VALUES (?)', ('페이징소비자',))
            consumer_id = cursor.lastrowid
            for _ in range(25):
                cursor.execute(
                    'INSERT INTO sales (merchandise_id, consumer_id, quantity_sold, unit_price, total_price) VALUES (?, ?, ?, ?, ?)',
                    (merchandise_id, consumer_id, 1, 100.0, 100.0)
                )
            db.commit()

        response = self.client.get('/api/sales?period=all&limit=20&offset=0')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['total'], 25)
        self.assertEqual(payload['limit'], 20)
        self.assertEqual(payload['offset'], 0)
        self.assertEqual(len(payload['sales']), 20)

    def test_get_sales_rejects_invalid_limit(self):
        response = self.client.get('/api/sales?period=all&limit=10&offset=0')
        self.assertEqual(response.status_code, 400)

    def test_update_consumer(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO consumers (name, phone, address, notes) VALUES (?, ?, ?, ?)',
                ('기존소비자', '010-1111-2222', '서울', '메모')
            )
            consumer_id = cursor.lastrowid
            db.commit()

        response = self.client.put(
            f'/api/consumers/{consumer_id}',
            json={'name': '수정소비자', 'phone': '010-9999-0000', 'address': '부산', 'notes': '수정메모'}
        )
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            consumer = db.execute('SELECT name, phone, address, notes FROM consumers WHERE id = ?', (consumer_id,)).fetchone()
        self.assertEqual(consumer['name'], '수정소비자')
        self.assertEqual(consumer['phone'], '010-9999-0000')
        self.assertEqual(consumer['address'], '부산')
        self.assertEqual(consumer['notes'], '수정메모')

    def test_update_consumer_returns_404_for_unknown_id(self):
        response = self.client.put(
            '/api/consumers/9999',
            json={'name': '없는소비자', 'phone': '', 'address': '', 'notes': ''}
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_sale_restores_inventory(self):
        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            cursor = db.cursor()
            cursor.execute(
                'INSERT INTO merchandise (name, description, quantity, price) VALUES (?, ?, ?, ?)',
                ('삭제테스트상품', '설명', 7, 100.0)
            )
            merchandise_id = cursor.lastrowid
            cursor.execute('INSERT INTO consumers (name) VALUES (?)', ('소비자',))
            consumer_id = cursor.lastrowid
            cursor.execute(
                'INSERT INTO sales (merchandise_id, consumer_id, quantity_sold, unit_price, total_price) VALUES (?, ?, ?, ?, ?)',
                (merchandise_id, consumer_id, 3, 100.0, 300.0)
            )
            sale_id = cursor.lastrowid
            db.commit()

        response = self.client.delete(f'/api/sales/{sale_id}')
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            merchandise = db.execute('SELECT quantity FROM merchandise WHERE id = ?', (merchandise_id,)).fetchone()
            sale = db.execute('SELECT id FROM sales WHERE id = ?', (sale_id,)).fetchone()

        self.assertEqual(merchandise['quantity'], 7)
        self.assertIsNone(sale)

    def test_backup_database_download(self):
        response = self.client.get('/api/config/backup')
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response.headers.get('Content-Disposition', ''))

    def test_backup_database_download_as_unsupported_format(self):
        response = self.client.get('/api/config/backup?format=parquet')
        self.assertEqual(response.status_code, 400)

    def test_restore_database_requires_file(self):
        response = self.client.post('/api/config/restore', data={})
        self.assertEqual(response.status_code, 400)

    def test_restore_database_rejects_parquet_file(self):
        with tempfile.NamedTemporaryFile(suffix='.parquet') as parquet_file:
            parquet_file.write(b'not-a-parquet')
            parquet_file.flush()
            with open(parquet_file.name, 'rb') as uploaded:
                response = self.client.post(
                    '/api/config/restore',
                    data={'database': (uploaded, 'backup.parquet')},
                    content_type='multipart/form-data'
                )
        self.assertEqual(response.status_code, 400)

    def test_timezone_config_defaults_to_asia_seoul(self):
        response = self.client.get('/api/config/timezone')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['timezone'], 'Asia/Seoul')

    def test_timezone_config_can_be_updated(self):
        response = self.client.post('/api/config/timezone', json={'timezone': 'UTC'})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['timezone'], 'UTC')

        read_back = self.client.get('/api/config/timezone')
        self.assertEqual(read_back.status_code, 200)
        self.assertEqual(read_back.get_json()['timezone'], 'UTC')

    def test_timezone_config_rejects_invalid_timezone(self):
        response = self.client.post('/api/config/timezone', json={'timezone': 'Not/A_Timezone'})
        self.assertEqual(response.status_code, 400)

    def test_authenticate_rejects_invalid_password(self):
        salesmanager.app.config['TESTING'] = False
        try:
            with patch.object(salesmanager, 'DEPLOYMENT_TYPE', 'public'):
                response = self.client.post('/api/authenticate', json={'password': 'wrong-password'})
        finally:
            salesmanager.app.config['TESTING'] = True
        self.assertEqual(response.status_code, 401)

    def test_authenticate_accepts_valid_password(self):
        salesmanager.app.config['TESTING'] = False
        try:
            with patch.object(salesmanager, 'DEPLOYMENT_TYPE', 'public'):
                response = self.client.post('/api/authenticate', json={'password': salesmanager.SITE_PASSWORD})
        finally:
            salesmanager.app.config['TESTING'] = True
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['message'], '인증되었습니다')

    def test_local_deployment_does_not_require_password(self):
        salesmanager.app.config['TESTING'] = False
        try:
            with patch.object(salesmanager, 'DEPLOYMENT_TYPE', 'local'):
                response = self.client.get('/api/merchandise')
        finally:
            salesmanager.app.config['TESTING'] = True
        self.assertEqual(response.status_code, 200)


class SalesManagerAutoInitTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, 'auto-init.db')
        salesmanager.DATABASE = self.db_path
        salesmanager.app.config['TESTING'] = True
        salesmanager.app.config['_DB_INITIALIZED'] = False
        self.client = salesmanager.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_consumer_creates_missing_tables_automatically(self):
        response = self.client.post('/api/consumers', json={'name': '신규소비자'})
        self.assertEqual(response.status_code, 200)

        with salesmanager.app.app_context():
            db = salesmanager.get_db()
            consumers = db.execute('SELECT name FROM consumers').fetchall()
            merchandise = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='merchandise'").fetchone()
            sales = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sales'").fetchone()

        self.assertEqual(consumers[0]['name'], '신규소비자')
        self.assertIsNotNone(merchandise)
        self.assertIsNotNone(sales)


class DateHelperTestCase(unittest.TestCase):
    def test_subtract_months_handles_year_boundary(self):
        reference = datetime(2026, 1, 15, 10, 30, 0)
        result = salesmanager.subtract_months(reference, 1)
        self.assertEqual(result, datetime(2025, 12, 15, 10, 30, 0))

    def test_subtract_months_clamps_day_to_last_day_of_month(self):
        reference = datetime(2026, 3, 31, 9, 0, 0)
        result = salesmanager.subtract_months(reference, 1)
        self.assertEqual(result, datetime(2026, 2, 28, 9, 0, 0))


class RunScriptTestCase(unittest.TestCase):
    def test_parse_args_supports_database_path_argument(self):
        args = run.parse_args(['--database-path', '/data/salesmanager.db'])
        self.assertEqual(args.database_path, '/data/salesmanager.db')

    def test_parse_args_uses_database_path_environment_default(self):
        with patch.dict(os.environ, {'DATABASE_PATH': '/mnt/data/sales.db'}):
            args = run.parse_args([])
        self.assertEqual(args.database_path, '/mnt/data/sales.db')

    def test_parse_args_supports_worker_class_argument(self):
        args = run.parse_args(['--worker-class', 'sync'])
        self.assertEqual(args.worker_class, 'sync')

    def test_parse_args_uses_worker_class_environment_default(self):
        with patch.dict(os.environ, {'GUNICORN_WORKER_CLASS': 'sync'}):
            args = run.parse_args([])
        self.assertEqual(args.worker_class, 'sync')

    def test_main_sets_database_path_and_starts_gunicorn(self):
        parsed_args = SimpleNamespace(
            database_path='/mnt/data/app.db',
            bind='127.0.0.1:5001',
            worker_class='gthread'
        )
        with patch('run.parse_args', return_value=parsed_args):
            with patch('app.init_db') as init_db:
                with patch('run.subprocess.call', return_value=0) as gunicorn_call:
                    with patch.dict(os.environ, {}, clear=False):
                        exit_code = run.main([])
                        database_path = os.environ.get('DATABASE_PATH')
        self.assertEqual(exit_code, 0)
        self.assertEqual(database_path, '/mnt/data/app.db')
        init_db.assert_called_once()
        gunicorn_call.assert_called_once_with([
            'gunicorn',
            '--bind', '127.0.0.1:5001',
            '--worker-class', 'gthread',
            'app:app'
        ])


class RoutingIntegrityTestCase(unittest.TestCase):
    def test_consumer_update_route_registered_once(self):
        rules = [
            rule for rule in salesmanager.app.url_map.iter_rules()
            if rule.rule == '/api/consumers/<int:consumer_id>' and 'PUT' in rule.methods
        ]
        self.assertEqual(len(rules), 1)


if __name__ == '__main__':
    unittest.main()
