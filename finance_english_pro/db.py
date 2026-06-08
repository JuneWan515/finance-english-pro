from __future__ import annotations

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "finance_english_pro.sqlite3"
SEED_CSV = BASE_DIR / "data" / "seed_terms.csv"
SOURCE_XLSX = BASE_DIR.parent / "整理文件" / "finance_accounting_english_extract.xlsx"
SOURCE_CSV = BASE_DIR.parent / "整理文件" / "finance_accounting_english_extract.csv"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]
