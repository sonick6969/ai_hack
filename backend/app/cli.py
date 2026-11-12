import argparse
import json
from pathlib import Path

from .config import CASE_FILE, DATABASE_PATH
from .db import connect, migrate
from .importer import import_excel


def main():
    parser = argparse.ArgumentParser(description='Локальное хранилище КофеСервис')
    parser.add_argument('command', choices=['migrate', 'import-case', 'import-excel'])
    parser.add_argument('file', nargs='?')
    args = parser.parse_args()
    migrate()
    if args.command == 'migrate':
        print(f'Миграции применены: {DATABASE_PATH}')
        return
    file = CASE_FILE if args.command == 'import-case' else Path(args.file or '')
    if not file.is_file():
        parser.error('Укажите существующий файл .xlsx')
    conn = connect()
    try:
        report = import_excel(conn, file.read_bytes(), file.name, 'case' if args.command == 'import-case' else 'upload', 'CLI')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        conn.close()
    if report['status'] != 'success':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
