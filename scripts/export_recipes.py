#!/usr/bin/env python3
"""Export per-dataset openapi download recipes for the GitHub Pages demo.

WARNING: each recipe embeds the dataset's durable NDAP openapi API_Key, which is
tied to the account that harvested it. Publishing this file exposes those keys.
Only export it for a demo where you accept that exposure.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export NDAP download recipes for the demo")
    parser.add_argument("--db", default="data/index.db", help="SQLite index path")
    parser.add_argument("--out", default="docs/assets/ndap_recipes.json", help="Output JSON path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    out_path = Path(args.out)

    if not db_path.exists():
        raise SystemExit(f"missing DB: {db_path}")

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT dataset_id, api_key, ind_csv, dim_csv
            FROM datasets
            WHERE api_key != '' AND ind_csv != '' AND dim_csv != ''
            ORDER BY dataset_id
            """
        ).fetchall()

    recipes = {str(r[0]): {"k": r[1], "i": r[2], "d": r[3]} for r in rows}

    payload = {
        "base": "https://loadqa.ndapapi.com/v1/openapi",
        "pageSize": 1000,
        "count": len(recipes),
        "recipes": recipes,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {len(recipes)} recipes to {out_path}")


if __name__ == "__main__":
    main()
