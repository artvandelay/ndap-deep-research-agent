#!/usr/bin/env python3
"""Harvest dataset metadata from NDAP /v1/sourcedetails endpoint."""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Iterable

import httpx

import ndap_auth
from schema import BASE

CATALOGUE_CSV = Path("data/catalogue.csv")
OUT_DIR = Path("data/sourcedetails")
MAX_RETRIES = 5
REQUEST_INTERVAL_SECONDS = 0.2
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Origin": "https://ndap.niti.gov.in",
    "Referer": "https://ndap.niti.gov.in/",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest NDAP sourcedetails metadata")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of datasets to process")
    parser.add_argument("--ids", type=str, default="", help="Comma-separated dataset IDs")
    return parser.parse_args()


def load_dataset_ids(ids_csv: str, limit: int | None) -> list[int]:
    if ids_csv.strip():
        ids = [int(item.strip()) for item in ids_csv.split(",") if item.strip()]
    else:
        if not CATALOGUE_CSV.exists():
            raise FileNotFoundError(f"Missing catalogue CSV: {CATALOGUE_CSV}")
        with CATALOGUE_CSV.open(newline="") as handle:
            reader = csv.DictReader(handle)
            ids = [int(row["dataset_id"]) for row in reader if row.get("dataset_id")]

    if limit is not None:
        return ids[: max(limit, 0)]
    return ids


def _invalid_token(payload: dict) -> bool:
    message = str(payload.get("Message", "")).lower()
    return "invalid token" in message


def _retry_delay(attempt: int) -> float:
    return min(8.0, 0.5 * (2 ** attempt))


def _fetch_one(client: httpx.Client, dataset_id: int) -> dict:
    url = f"{BASE}/v1/sourcedetails"
    payload = {"ip_sourceid": [int(dataset_id)]}
    refreshed = False

    for attempt in range(MAX_RETRIES):
        token = ndap_auth.get_access_token()
        headers = {**BASE_HEADERS, "Authorization": f"Bearer {token}"}
        try:
            response = client.post(url, json=payload, headers=headers)
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
        data = response.json()
        if _invalid_token(data):
            if refreshed:
                raise RuntimeError(f"Invalid token persisted for dataset {dataset_id}")
            ndap_auth.refresh()
            refreshed = True
            continue
        if "sourcedetails" not in data:
            raise RuntimeError(
                f"Unexpected sourcedetails response for dataset {dataset_id}: {data.get('Message', 'no message')}"
            )
        return data

    raise RuntimeError(f"Exceeded retries for dataset {dataset_id}")


def _iter_targets(dataset_ids: Iterable[int]) -> list[tuple[int, Path]]:
    targets: list[tuple[int, Path]] = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for dataset_id in dataset_ids:
        target_path = OUT_DIR / f"{dataset_id}.json"
        targets.append((dataset_id, target_path))
    return targets


def main() -> None:
    args = parse_args()
    dataset_ids = load_dataset_ids(args.ids, args.limit)
    targets = _iter_targets(dataset_ids)

    downloaded = 0
    skipped = 0
    failed = 0
    processed = 0

    with httpx.Client(timeout=60.0) as client:
        for dataset_id, target_path in targets:
            if target_path.exists() and target_path.stat().st_size > 0:
                skipped += 1
            else:
                try:
                    data = _fetch_one(client, dataset_id)
                    target_path.write_text(json.dumps(data, indent=2))
                    downloaded += 1
                except Exception as exc:
                    failed += 1
                    print(f"[failed] dataset {dataset_id}: {exc}")

            processed += 1
            if processed % 200 == 0:
                print(
                    f"[progress] processed={processed}/{len(targets)} "
                    f"downloaded={downloaded} skipped={skipped} failed={failed}"
                )
            time.sleep(REQUEST_INTERVAL_SECONDS)

    print(
        f"[done] processed={processed} downloaded={downloaded} "
        f"skipped={skipped} failed={failed}"
    )


if __name__ == "__main__":
    main()
