import argparse
import os
import subprocess


def _int_env(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Run Sales Manager server')
    parser.add_argument(
        '--database-path',
        default=os.environ.get('DATABASE_PATH', 'database/salesmanager.db'),
        help='Path to SQLite database file'
    )
    parser.add_argument(
        '--bind',
        default='0.0.0.0:5000',
        help='Gunicorn bind address'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=_int_env('GUNICORN_TIMEOUT', 120),
        help='Gunicorn worker timeout in seconds'
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    os.environ['DATABASE_PATH'] = args.database_path
    from app import init_db

    init_db()
    return subprocess.call([
        'gunicorn',
        '--bind', args.bind,
        '--timeout', str(args.timeout),
        'app:app'
    ])


if __name__ == '__main__':
    raise SystemExit(main())
