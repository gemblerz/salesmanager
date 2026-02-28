import argparse
import os
import subprocess


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Run Sales Manager server')
    parser.add_argument(
        '--database-path',
        default=os.environ.get('DATABASE_PATH', 'salesmanager.db'),
        help='Path to SQLite database file'
    )
    parser.add_argument(
        '--bind',
        default='0.0.0.0:5000',
        help='Gunicorn bind address'
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    os.environ['DATABASE_PATH'] = args.database_path
    from app import init_db

    init_db()
    return subprocess.call(['gunicorn', '--bind', args.bind, 'app:app'])


if __name__ == '__main__':
    raise SystemExit(main())
