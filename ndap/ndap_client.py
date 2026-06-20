"""NDAP API client for catalogue and dataset downloads."""

from __future__ import annotations

import csv
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

NDAP_API = "https://loadqa.ndapapi.com"
NDAP_SITE = "https://ndap.niti.gov.in"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Origin": NDAP_SITE,
    "Referer": f"{NDAP_SITE}/",
    "Accept": "application/json, text/plain, */*",
}


class NDAPClient:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("NDAP_TOKEN")
        self._client = httpx.Client(headers=DEFAULT_HEADERS, timeout=120)

    def _headers(self) -> dict[str, str]:
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def get_metadata(self) -> dict[str, Any]:
        r = self._client.get(f"{NDAP_API}/v1/metadata?domain=ndap", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def get_catalogue(self) -> dict[str, Any]:
        r = self._client.get(
            f"{NDAP_API}/v1/search/catalogue",
            params={"query": "*", "search": "Variables,DatasetInfo", "domain": "ndap"},
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    def flatten_catalogue(self, catalogue: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for coll in catalogue.get("Records", {}).get("results", []):
            for ds in coll.get("details", []):
                ds_id = ds.get("id")
                if not ds_id:
                    continue
                meta = ds.get("details", ds)
                if "ministry" not in meta and isinstance(ds.get("details"), dict):
                    meta = ds["details"]
                rows.append(
                    {
                        "collection": coll["name"],
                        "dataset_id": ds_id,
                        "dataset_name": ds["name"],
                        "ministry": meta.get("ministry", ""),
                        "sector": meta.get("sector", ""),
                        "frequency": meta.get("frequency", ""),
                        "starting_year": meta.get("startingYear", ""),
                        "ending_year": meta.get("endingYear", ""),
                        "last_updated": meta.get("LastUpdatedDate", ""),
                        "columns": meta.get("noOfColumns", ""),
                        "location_granularity": ds.get("LocationGranularity", ""),
                        "url": f"{NDAP_SITE}/dataset/{ds_id}",
                    }
                )
        return rows

    def save_catalogue(self, out_dir: Path) -> tuple[Path, Path, int]:
        out_dir.mkdir(parents=True, exist_ok=True)
        catalogue = self.get_catalogue()
        rows = self.flatten_catalogue(catalogue)

        json_path = out_dir / "catalogue.json"
        csv_path = out_dir / "catalogue.csv"

        json_path.write_text(json.dumps(catalogue, indent=2))
        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)

        return json_path, csv_path, len(rows)

    def get_dataset_details(self, dataset_id: str) -> dict[str, Any]:
        r = self._client.post(
            f"{NDAP_API}/v1/dataset/details",
            json={"ip_id": dataset_id, "domain": "ndap"},
            headers={**DEFAULT_HEADERS, "Content-Type": "application/json", **self._headers()},
        )
        r.raise_for_status()
        return r.json()

    def download_dataset(
        self,
        dataset_id: str,
        *,
        limit: int = 100_000,
        offset: int = 0,
    ) -> httpx.Response:
        payload = {
            "ip_sourceid": [dataset_id],
            "ip_columns": {},
            "ip_filter": [],
            "ip_orderby": [],
            "ip_sourcemaster": 1,
            "ip_datavariables": 1,
            "ip_datasetprofile": 1,
            "ip_limit": limit,
            "ip_offset": offset,
            "view_name": "",
            "domain": "ndap",
        }
        return self._client.post(
            f"{NDAP_API}/v1/dataset/download",
            json=payload,
            headers={**DEFAULT_HEADERS, "Content-Type": "application/json", **self._headers()},
        )

    def export_dataset(self, dataset_id: str, fmt: str = "csv") -> httpx.Response:
        return self._client.get(
            f"{NDAP_API}/v1/dataset/export",
            params={"ip_sourceid": dataset_id, "format": fmt, "domain": "ndap"},
            headers=self._headers(),
        )

    def bulk_download(
        self,
        dataset_ids: list[str],
        out_dir: Path,
        *,
        delay: float = 0.5,
    ) -> tuple[list[str], list[str]]:
        if not self.token:
            raise ValueError("NDAP_TOKEN required for dataset downloads")

        out_dir.mkdir(parents=True, exist_ok=True)
        ok, failed = [], []

        for i, ds_id in enumerate(dataset_ids, 1):
            safe_id = re.sub(r"[^\w\-]", "_", ds_id)
            dest = out_dir / f"{safe_id}.json"
            if dest.exists() and dest.stat().st_size > 0:
                ok.append(str(dest))
                continue

            try:
                r = self.download_dataset(ds_id)
                if r.status_code != 200:
                    failed.append(f"{ds_id}: HTTP {r.status_code}")
                    continue
                data = r.json()
                if data.get("Message") == "Token Required":
                    failed.append(f"{ds_id}: token required")
                    continue
                dest.write_text(json.dumps(data, indent=2))
                ok.append(str(dest))
                if i % 50 == 0:
                    print(f"  downloaded {i}/{len(dataset_ids)}")
            except Exception as exc:
                failed.append(f"{ds_id}: {exc}")

            time.sleep(delay)

        return ok, failed

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NDAPClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
