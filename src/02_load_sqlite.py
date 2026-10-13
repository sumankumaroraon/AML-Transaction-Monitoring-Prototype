"""
02_load_sqlite.py
Create the SQLite database, load the synthetic CSVs and the ground-truth labels,
and seed analyst reviews.
"""
import pandas as pd

from common import DB_PATH, ROOT, SQL_DIR, connect

RAW = ROOT / "data" / "raw"
LABELS = ROOT / "data" / "labels"
SEED_REVIEWS = ROOT / "data" / "reviews" / "seed_reviews.csv"


def main():
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = connect()
    conn.executescript((SQL_DIR / "00_schema.sql").read_text())

    tx = pd.read_csv(RAW / "transactions.csv").rename(columns={"timestamp": "ts"})
    loads = {
        "customers": pd.read_csv(RAW / "customers.csv"),
        "accounts": pd.read_csv(RAW / "accounts.csv"),
        "transactions": tx,
        "planted_scenarios": pd.read_csv(LABELS / "planted_scenarios.csv"),
        "planted_transactions": pd.read_csv(LABELS / "planted_transactions.csv"),
        "benign_lookalikes": pd.read_csv(LABELS / "benign_lookalikes.csv"),
    }
    for table, df in loads.items():
        df.to_sql(table, conn, if_exists="append", index=False)
        print(f"loaded {table:22s} {len(df):>7,} rows")

    if SEED_REVIEWS.exists():
        rv = pd.read_csv(SEED_REVIEWS)
        rv.to_sql("alert_reviews", conn, if_exists="append", index=False)
        print(f"seeded alert_reviews        {len(rv):>7,} rows")
    conn.executescript((SQL_DIR / "05_reporting_views.sql").read_text())
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
