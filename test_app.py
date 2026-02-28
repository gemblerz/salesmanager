import os
import tempfile
import unittest
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

        self.assertEqual(merchandise['quantity'], 5)
        self.assertEqual(sale['quantity_sold'], 5)
        self.assertEqual(sale['consumer_id'], consumer_id_2)
        self.assertEqual(sale['total_price'], 500.0)

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

        self.assertEqual(merchandise['quantity'], 10)
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


class RunScriptTestCase(unittest.TestCase):
    def test_parse_args_supports_database_path_argument(self):
        args = run.parse_args(['--database-path', '/data/salesmanager.db'])
        self.assertEqual(args.database_path, '/data/salesmanager.db')

    def test_parse_args_uses_database_path_environment_default(self):
        with patch.dict(os.environ, {'DATABASE_PATH': '/mnt/data/sales.db'}):
            args = run.parse_args([])
        self.assertEqual(args.database_path, '/mnt/data/sales.db')

    def test_main_sets_database_path_and_starts_gunicorn(self):
        parsed_args = SimpleNamespace(database_path='/mnt/data/app.db', bind='127.0.0.1:5001')
        with patch('run.parse_args', return_value=parsed_args):
            with patch('app.init_db') as init_db:
                with patch('run.subprocess.call', return_value=0) as gunicorn_call:
                    with patch.dict(os.environ, {}, clear=False):
                        exit_code = run.main([])
                        database_path = os.environ.get('DATABASE_PATH')
        self.assertEqual(exit_code, 0)
        self.assertEqual(database_path, '/mnt/data/app.db')
        init_db.assert_called_once()
        gunicorn_call.assert_called_once_with(['gunicorn', '--bind', '127.0.0.1:5001', 'app:app'])


if __name__ == '__main__':
    unittest.main()
