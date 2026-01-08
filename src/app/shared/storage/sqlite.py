from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def _read_schema() -> str:
    schema_path = Path(__file__).with_name("schema.sql")
    return schema_path.read_text(encoding="utf-8")


def ensure_sqlite(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    schema_sql = _read_schema()
    conn.executescript(schema_sql)
    conn.commit()

    return conn
