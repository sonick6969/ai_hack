import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
DATABASE_PATH = Path(os.getenv('DATABASE_PATH', str(ROOT / 'data' / 'pilot.sqlite3')))
CASE_FILE = ROOT / 'Данные_к_кейсу_06 (1).xlsx'
FRONTEND_DIST = ROOT / 'frontend' / 'dist'
