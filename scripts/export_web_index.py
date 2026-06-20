#!/usr/bin/env python3
"""Export a browser-friendly search index from data/index.db."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export NDAP metadata for the GitHub Pages demo")
    parser.add_argument("--db", default="data/index.db", help="SQLite index path")
    parser.add_argument("--out", default="docs/assets/ndap_index.json", help="Output JSON path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    out_path = Path(args.out)

    if not db_path.exists():
        raise SystemExit(f"missing DB: {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                dataset_id,
                name,
                COALESCE(description, '') AS description,
                COALESCE(sector, '') AS sector,
                COALESCE(ministry, '') AS ministry,
                from_year,
                to_year,
                COALESCE(geo_levels, '') AS geo,
                COALESCE(temporal_levels, '') AS time,
                n_indicators,
                n_dimensions
            FROM datasets
            ORDER BY dataset_id
            """
        ).fetchall()

    items = []
    for row in rows:
        from_year = row["from_year"]
        to_year = row["to_year"]
        years = ""
        if from_year and to_year:
            years = f"{from_year}-{to_year}"
        elif from_year:
            years = str(from_year)

        items.append(
            {
                "id": row["dataset_id"],
                "name": row["name"],
                "description": row["description"],
                "sector": row["sector"],
                "ministry": row["ministry"],
                "years": years,
                "geo": row["geo"],
                "time": row["time"],
                "nIndicators": row["n_indicators"],
                "nDimensions": row["n_dimensions"],
            }
        )

    payload = {
        "generatedFrom": str(db_path),
        "datasetCount": len(items),
        "items": items,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {len(items)} datasets to {out_path}")


if __name__ == "__main__":
    main()
