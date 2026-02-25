import os
import tempfile
import unittest

import app as salesmanager


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


if __name__ == '__main__':
    unittest.main()
