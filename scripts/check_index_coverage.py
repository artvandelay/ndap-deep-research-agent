#!/usr/bin/env python3
"""Check whether data/index.db covers every row in data/catalogue.csv."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check NDAP catalogue coverage in the SQLite index")
    parser.add_argument("--db", default="data/index.db", help="SQLite index path")
    parser.add_argument("--catalogue", default="data/catalogue.csv", help="NDAP catalogue CSV path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    catalogue_path = Path(args.catalogue)

    if not db_path.exists():
        raise SystemExit(f"missing DB: {db_path}")
    if not catalogue_path.exists():
        raise SystemExit(f"missing catalogue: {catalogue_path}")

    with sqlite3.connect(db_path) as conn:
        db_ids = {int(row[0]) for row in conn.execute("SELECT dataset_id FROM datasets")}
        catalogue_only = {
            int(row[0])
            for row in conn.execute(
                """
                SELECT dataset_id
                FROM datasets
                WHERE n_indicators = 0
                  AND n_dimensions = 0
                  AND notes LIKE 'Catalogue-only row;%'
                """
            )
        }

    with catalogue_path.open(newline="") as handle:
        catalogue_ids = {
            int(row["dataset_id"])
            for row in csv.DictReader(handle)
            if row.get("dataset_id")
        }

    missing = sorted(catalogue_ids - db_ids)
    extra = sorted(db_ids - catalogue_ids)

    print(f"catalogue_rows={len(catalogue_ids)}")
    print(f"db_rows={len(db_ids)}")
    print(f"missing_from_db={len(missing)} {missing}")
    print(f"extra_in_db={len(extra)} {extra}")
    print(f"catalogue_only_rows={len(catalogue_only)} {sorted(catalogue_only)}")

    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
