#!/usr/bin/env python3
"""On-demand NDAP dataset downloader via paginated /v1/openapi."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import httpx

import schema

FIXTURE_7171 = Path("data/fixtures/openapi_7171.json")
PAGE_SIZE = 1000
MAX_RETRIES = 5
REQUEST_INTERVAL_SECONDS = 0.2


def _retry_delay(attempt: int) -> float:
    return min(8.0, 0.5 * (2 ** attempt))


def _read_recipe_from_index(dataset_id: int) -> tuple[str, str, str] | None:
    db_path = Path(schema.INDEX_DB_PATH)
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT api_key, ind_csv, dim_csv FROM datasets WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
    if not row:
        return None
    api_key, ind_csv, dim_csv = row
    if not api_key or not ind_csv or not dim_csv:
        return None
    return str(api_key), str(ind_csv), str(dim_csv)


def _read_fixture_recipe(dataset_id: int) -> tuple[str, str, str] | None:
    if dataset_id != 7171 or not FIXTURE_7171.exists():
        return None
    payload = json.loads(FIXTURE_7171.read_text())
    return payload.get("api_key", ""), payload.get("ind", ""), payload.get("dim", "")


def _resolve_recipe(
    dataset_id: int,
    api_key: str | None,
    ind: str | None,
    dim: str | None,
) -> tuple[str, str, str]:
    if api_key and ind and dim:
        return api_key, ind, dim

    from_index = _read_recipe_from_index(dataset_id)
    if from_index:
        return from_index

    from_fixture = _read_fixture_recipe(dataset_id)
    if from_fixture and all(from_fixture):
        return from_fixture

    raise RuntimeError(
        "Download recipe unavailable. Build data/index.db first or provide --api-key, --ind, and --dim."
    )


def _extract_headers(payload: dict[str, Any]) -> list[str]:
    header_items = payload.get("Headers", {}).get("Items", []) or []
    headers = []
    for item in header_items:
        if not isinstance(item, dict):
            continue
        header_id = str(item.get("ID", "")).strip()
        display_name = str(item.get("DisplayName", "")).strip()
        headers.append(header_id or display_name)
    return [column for column in headers if column]


def _extract_rows(payload: dict[str, Any], headers: list[str]) -> list[list[Any]]:
    rows = payload.get("Data", []) or []
    output: list[list[Any]] = []
    for row in rows:
        if isinstance(row, dict):
            output.append([row.get(column, "") for column in headers])
        elif isinstance(row, list):
            output.append(row)
        else:
            output.append([row])
    return output


def _fetch_page(client: httpx.Client, url: str) -> dict[str, Any]:
    headers = {"User-Agent": "Mozilla/5.0"}
    for attempt in range(MAX_RETRIES):
        try:
            response = client.get(url, headers=headers)
        except httpx.HTTPError:
            if attempt >= MAX_RETRIES - 1:
                raise
            time.sleep(_retry_delay(attempt))
            continue

        if response.status_code in (429, 500, 502, 503, 504):
            if attempt >= MAX_RETRIES - 1:
                response.raise_for_status()
            time.sleep(_retry_delay(attempt))
            continue

        response.raise_for_status()
        return response.json()

    raise RuntimeError(f"Failed to fetch openapi page after {MAX_RETRIES} retries: {url}")


def download_dataset(
    dataset_id: int,
    out_dir: str = "data/datasets",
    *,
    api_key: str | None = None,
    ind: str | None = None,
    dim: str | None = None,
) -> str:
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{dataset_id}.csv"

    if output_path.exists() and output_path.stat().st_size > 0:
        return str(output_path)

    recipe_api_key, recipe_ind, recipe_dim = _resolve_recipe(dataset_id, api_key, ind, dim)

    with httpx.Client(timeout=60.0) as client, output_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        pageno = 1
        wrote_header = False
        csv_headers: list[str] = []

        while True:
            url = schema.build_openapi_url(recipe_api_key, recipe_ind, recipe_dim, pageno=pageno)
            payload = _fetch_page(client, url)

            if not wrote_header:
                csv_headers = _extract_headers(payload)
                if not csv_headers:
                    raise RuntimeError(f"Missing Headers.Items in /v1/openapi response for dataset {dataset_id}")
                writer.writerow(csv_headers)
                wrote_header = True

            rows = _extract_rows(payload, csv_headers)
            for row in rows:
                writer.writerow(row)

            if not rows or len(rows) < PAGE_SIZE:
                break

            pageno += 1
            time.sleep(REQUEST_INTERVAL_SECONDS)

    return str(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download one NDAP dataset as cached CSV")
    parser.add_argument("dataset_id", nargs="?", type=int, help="Dataset ID")
    parser.add_argument("--out", default="data/datasets", help="Output directory")
    parser.add_argument("--api-key", default=None, help="Explicit API key override")
    parser.add_argument("--ind", default=None, help="Explicit indicator CSV override")
    parser.add_argument("--dim", default=None, help="Explicit dimension CSV override")
    parser.add_argument("--selftest", action="store_true", help="Run self-test using dataset 7171")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_id = 7171 if args.selftest else args.dataset_id
    if dataset_id is None:
        raise SystemExit("dataset_id is required unless --selftest is provided")

    path = download_dataset(
        dataset_id=dataset_id,
        out_dir=args.out,
        api_key=args.api_key,
        ind=args.ind,
        dim=args.dim,
    )
    print(path)


if __name__ == "__main__":
    main()
