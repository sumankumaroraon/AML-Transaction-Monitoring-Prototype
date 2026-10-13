"""Shared helpers: paths, config, SQL file loading, DB connection."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "aml_monitoring.db"
SQL_DIR = ROOT / "sql"
OUT_DIR = ROOT / "outputs"
CONFIG_PATH = ROOT / "config" / "rules_config.json"

RULE_FILES = {
    "R1_RAPID_PASS_THROUGH": "01_rule_rapid_pass_through.sql",
    "R2_ACTIVITY_SPIKE": "02_rule_activity_spike.sql",
    "R3_MANY_TO_ONE": "03_rule_many_to_one.sql",
    "R4_STRUCTURING": "04_rule_structuring.sql",
}
RULE_LABELS = {
    "R1_RAPID_PASS_THROUGH": "R1 Rapid pass-through",
    "R2_ACTIVITY_SPIKE": "R2 Activity spike",
    "R3_MANY_TO_ONE": "R3 Many-to-one beneficiary",
    "R4_STRUCTURING": "R4 Below-threshold structuring",
}


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def named_sql(filename: str) -> dict[str, str]:
    """Split a .sql file into named statements using '-- name: <x>' markers."""
    text = (SQL_DIR / filename).read_text()
    parts = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1].strip().rstrip(";") for i in range(1, len(parts), 2)}
