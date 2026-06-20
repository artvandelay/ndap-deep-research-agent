#!/usr/bin/env python3
"""Build SQLite + FTS index from harvested NDAP sourcedetails JSON."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import schema

SUMMARY_PATH = Path("data/index_summary.json")
GEO_LEVEL_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("country", ("country",)),
    ("state", ("state", "province", "ut", "union territory")),
    ("district", ("district",)),
    ("subdistrict", ("subdistrict", "sub district", "tehsil", "taluka")),
    ("block", ("block",)),
    ("village", ("village",)),
    ("city", ("city", "town")),
    ("pincode", ("pincode", "pin code", "postal code", "zipcode", "zip code")),
]
TEMPORAL_LEVEL_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("year", ("year", "fy", "financial year", "annual")),
    ("quarter", ("quarter", "q1", "q2", "q3", "q4")),
    ("month", ("month", "monthly")),
    ("week", ("week", "weekly")),
    ("day", ("date", "day", "daily")),
]
KEY_DIMENSION_KEYWORDS = {
    "gender",
    "sex",
    "age",
    "caste",
    "religion",
    "category",
    "group",
}

# Strip NDAP's noisy "Units : [..] Scaling : [..]" suffixes from indicator labels.
_INDICATOR_NOISE_RE = re.compile(r"\s*(Units?|Scaling)\s*:\s*\[[^\]]*\]", re.IGNORECASE)

# Lexical FTS5 cannot infer meaning; inject related terms so topical queries hit.
SYNONYM_MAP: dict[str, tuple[str, ...]] = {
    "fertiliser": ("fertilizer", "urea", "npk", "nutrient"),
    "fertilizer": ("fertiliser", "urea", "npk", "nutrient"),
    "slum": ("informal settlement", "jhuggi", "shanty", "urban poverty"),
    "literacy": ("education", "schooling", "literate", "enrolment"),
    "school": ("education", "enrolment", "student"),
    "dbt": ("direct benefit transfer", "subsidy", "welfare", "cash transfer"),
    "crop": ("agriculture", "farming", "cultivation", "harvest"),
    "yield": ("productivity", "output per hectare"),
    "rainfall": ("precipitation", "monsoon", "rain"),
    "pollution": ("air quality", "pm2.5", "pm10", "emission"),
    "mortality": ("death", "fatality"),
    "birth": ("natality", "fertility"),
    "employment": ("jobs", "workforce", "labour", "labor"),
    "poverty": ("bpl", "below poverty line", "deprivation"),
    "gdp": ("gross domestic product", "economic output", "gsdp"),
    "power": ("electricity", "energy"),
    "coal": ("mining", "mineral"),
    "health": ("medical", "healthcare", "disease"),
    "bank": ("banking", "credit", "deposit", "financial"),
    "population": ("demographic", "census", "people"),
    "crime": ("offence", "ipc", "police"),
}


def _clean_label(text: str) -> str:
    text = _INDICATOR_NOISE_RE.sub("", text or "")
    return re.sub(r"\s+", " ", text).strip(" .;:-")


def _expand_synonyms(text: str) -> list[str]:
    low = text.lower()
    extra: list[str] = []
    for key, syns in SYNONYM_MAP.items():
        if key in low:
            extra.extend(syns)
    return _unique_non_empty(extra)


def _compose_description(
    dataset_row: dict[str, Any],
    ind_rows: list[dict[str, Any]],
    dim_rows: list[dict[str, Any]],
) -> str:
    """Build a dense ~12-18 word human-readable summary of one dataset."""

    topics = _unique_non_empty([_clean_label(r["display_name"]) for r in ind_rows])[:4]
    geo = (dataset_row.get("geo_levels") or dataset_row.get("granularity") or "").replace(",", "/")
    fy, ty = dataset_row.get("from_year"), dataset_row.get("to_year")
    years = f"{fy}-{ty}" if fy and ty else (str(fy) if fy else "")

    parts: list[str] = []
    if dataset_row.get("sector"):
        parts.append(dataset_row["sector"])
    if topics:
        parts.append("measures: " + ", ".join(topics))
    if geo:
        parts.append("by " + geo)
    if years:
        parts.append(years)
    if dataset_row.get("ministry"):
        parts.append(dataset_row["ministry"])
    return "; ".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build NDAP metadata index")
    parser.add_argument("--src", default="data/sourcedetails", help="Directory containing sourcedetails JSON files")
    parser.add_argument(
        "--catalogue",
        default="data/catalogue.csv",
        help=(
            "Optional NDAP catalogue CSV. Rows missing from sourcedetails are added as "
            "catalogue-only metadata records so the DB covers the full catalogue."
        ),
    )
    return parser.parse_args()


def reset_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS datasets;
        DROP TABLE IF EXISTS indicators;
        DROP TABLE IF EXISTS dimensions;
        DROP TABLE IF EXISTS datasets_fts;
        """
    )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema.DDL_DATASETS)
    conn.executescript(schema.DDL_INDICATORS)
    conn.executescript(schema.DDL_DIMENSIONS)
    conn.executescript(schema.DDL_FTS)


def _norm_text(*parts: str) -> str:
    return " ".join(part.strip().lower() for part in parts if part).strip()


def _infer_geo_level(text: str) -> str:
    for level, needles in GEO_LEVEL_KEYWORDS:
        if any(needle in text for needle in needles):
            return level
    return ""


def _infer_temporal_level(text: str) -> str:
    for level, needles in TEMPORAL_LEVEL_KEYWORDS:
        if any(needle in text for needle in needles):
            return level
    return ""


def _infer_dimension_enrichment(dim: schema.DimensionMeta) -> tuple[dict[str, Any], str]:
    row = dim.model_dump()
    text = _norm_text(dim.display_name, dim.dim_id, dim.dim_type, dim.description)
    geo_level = _infer_geo_level(text)
    temporal_level = _infer_temporal_level(text)

    if geo_level:
        canonical_group = "geographic"
    elif temporal_level:
        canonical_group = "temporal"
    else:
        canonical_group = "other"

    if "lgd" in text or "local government directory" in text:
        code_standard = "LGD"
    elif "iso" in text:
        code_standard = "ISO"
    elif "census" in text:
        code_standard = "Census"
    elif "code" in text and geo_level:
        code_standard = "Administrative code"
    else:
        code_standard = ""

    is_key_dimension = canonical_group in {"geographic", "temporal"} or any(
        keyword in text for keyword in KEY_DIMENSION_KEYWORDS
    )

    row.update(
        canonical_group=canonical_group,
        is_key_dimension=is_key_dimension,
        geo_level=geo_level,
        code_standard=code_standard,
    )
    return row, temporal_level


def _infer_indicator_enrichment(ind: schema.IndicatorMeta, dataset_sector: str) -> dict[str, Any]:
    row = ind.model_dump()
    text = _norm_text(ind.display_name, ind.description)

    if "index" in text:
        variable_class = "index"
    elif "rate" in text or "ratio" in text or "percent" in text or "%" in text:
        variable_class = "rate"
    elif "count" in text or "number of" in text:
        variable_class = "count"
    elif "amount" in text or "value" in text:
        variable_class = "value"
    else:
        variable_class = "measure"

    weight_variable = "weight" in text or "weighted" in text
    if "female" in text or "women" in text or "girl" in text:
        if "male" in text or "men" in text or "boy" in text:
            weight_scope_gender = "both"
        else:
            weight_scope_gender = "female"
    elif "male" in text or "men" in text or "boy" in text:
        weight_scope_gender = "male"
    elif "gender" in text or "sex" in text:
        weight_scope_gender = "gender"
    else:
        weight_scope_gender = ""

    row.update(
        variable_class=variable_class,
        weight_variable=weight_variable,
        weight_scope_sector=dataset_sector if weight_variable else "",
        weight_scope_gender=weight_scope_gender,
    )
    return row


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _enrich_metadata(
    dataset: schema.DatasetMeta,
    indicators: list[schema.IndicatorMeta],
    dimensions: list[schema.DimensionMeta],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], str]:
    dim_rows: list[dict[str, Any]] = []
    temporal_levels: list[str] = []
    geo_levels: list[str] = []

    for dim in dimensions:
        dim_row, temporal_level = _infer_dimension_enrichment(dim)
        dim_rows.append(dim_row)
        if temporal_level:
            temporal_levels.append(temporal_level)
        if dim_row["geo_level"]:
            geo_levels.append(dim_row["geo_level"])

    ind_rows = [_infer_indicator_enrichment(ind, dataset.sector) for ind in indicators]

    key_dimensions = _unique_non_empty([row["dim_id"] for row in dim_rows if row["is_key_dimension"]])
    geo_levels_unique = _unique_non_empty(geo_levels)
    temporal_levels_unique = _unique_non_empty(temporal_levels)

    geo_standard = ""
    granularity_text = _norm_text(dataset.granularity)
    if "lgd" in granularity_text or any(row["code_standard"] == "LGD" for row in dim_rows):
        geo_standard = "LGD"

    if geo_standard == "LGD":
        mapping_basis = "LGD code mapping"
    elif geo_levels_unique:
        mapping_basis = "Geographic dimension mapping"
    else:
        mapping_basis = ""
    if mapping_basis and temporal_levels_unique:
        mapping_basis += " + temporal buckets"

    dataset_row = dataset.model_dump()
    dataset_row.update(
        geo_standard=geo_standard,
        key_dimensions=",".join(key_dimensions),
        geo_levels=",".join(geo_levels_unique),
        temporal_levels=",".join(temporal_levels_unique),
        mapping_basis=mapping_basis,
    )

    description = _compose_description(dataset_row, ind_rows, dim_rows)
    dataset_row["description"] = description

    synonym_source = _norm_text(
        dataset_row["name"],
        dataset_row.get("sector", ""),
        dataset_row.get("ministry", ""),
        description,
        " ".join(_clean_label(row["display_name"]) for row in ind_rows),
        " ".join(row["display_name"] for row in dim_rows),
    )
    synonyms = _expand_synonyms(synonym_source)

    enrichment_chunks = [
        dataset_row["geo_standard"],
        dataset_row["key_dimensions"],
        dataset_row["geo_levels"],
        dataset_row["temporal_levels"],
        dataset_row["mapping_basis"],
        " ".join(row["variable_class"] for row in ind_rows if row["variable_class"]),
        " ".join(row["canonical_group"] for row in dim_rows if row["canonical_group"]),
        " ".join(row["code_standard"] for row in dim_rows if row["code_standard"]),
        dataset_row.get("sector", ""),
        dataset_row.get("ministry", ""),
        dataset_row.get("department", ""),
        description,
        " ".join(synonyms),
    ]
    enrichment_text = " ".join(chunk for chunk in enrichment_chunks if chunk).strip()

    return dataset_row, ind_rows, dim_rows, enrichment_text


def insert_payload(conn: sqlite3.Connection, raw: dict) -> None:
    dataset, indicators, dimensions = schema.parse_sourcedetails(raw)
    dataset_row, indicator_rows, dimension_rows, enrichment_text = _enrich_metadata(
        dataset, indicators, dimensions
    )

    conn.execute(
        """
        INSERT INTO datasets (
            dataset_id, name, sector, ministry, department, granularity, from_year, to_year,
            update_frequency, n_columns, source_link, notes, geo_standard, key_dimensions,
            geo_levels, temporal_levels, mapping_basis, description, api_key, ind_csv, dim_csv,
            n_indicators, n_dimensions
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_row["dataset_id"],
            dataset_row["name"],
            dataset_row["sector"],
            dataset_row["ministry"],
            dataset_row["department"],
            dataset_row["granularity"],
            dataset_row["from_year"],
            dataset_row["to_year"],
            dataset_row["update_frequency"],
            dataset_row["n_columns"],
            dataset_row["source_link"],
            dataset_row["notes"],
            dataset_row["geo_standard"],
            dataset_row["key_dimensions"],
            dataset_row["geo_levels"],
            dataset_row["temporal_levels"],
            dataset_row["mapping_basis"],
            dataset_row["description"],
            dataset_row["api_key"],
            dataset_row["ind_csv"],
            dataset_row["dim_csv"],
            dataset_row["n_indicators"],
            dataset_row["n_dimensions"],
        ),
    )

    if indicator_rows:
        conn.executemany(
            """
            INSERT INTO indicators (
                dataset_id, ind_id, display_name, data_type, units, scaling, description,
                variable_class, weight_variable, weight_scope_sector, weight_scope_gender
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["dataset_id"],
                    row["ind_id"],
                    row["display_name"],
                    row["data_type"],
                    row["units"],
                    row["scaling"],
                    row["description"],
                    row["variable_class"],
                    1 if row["weight_variable"] else 0,
                    row["weight_scope_sector"],
                    row["weight_scope_gender"],
                )
                for row in indicator_rows
            ],
        )

    if dimension_rows:
        conn.executemany(
            """
            INSERT INTO dimensions (
                dataset_id, dim_id, display_name, data_type, dim_type, description,
                canonical_group, is_key_dimension, geo_level, code_standard
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["dataset_id"],
                    row["dim_id"],
                    row["display_name"],
                    row["data_type"],
                    row["dim_type"],
                    row["description"],
                    row["canonical_group"],
                    1 if row["is_key_dimension"] else 0,
                    row["geo_level"],
                    row["code_standard"],
                )
                for row in dimension_rows
            ],
        )

    indicator_names = " ".join(row["display_name"] for row in indicator_rows if row["display_name"])
    dimension_names = " ".join(row["display_name"] for row in dimension_rows if row["display_name"])
    conn.execute(
        """
        INSERT INTO datasets_fts (
            dataset_id, name, notes, indicator_names, dimension_names, enrichment_text
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_row["dataset_id"],
            dataset_row["name"],
            dataset_row["notes"],
            indicator_names,
            dimension_names,
            enrichment_text,
        ),
    )


def _catalogue_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def insert_catalogue_fallbacks(conn: sqlite3.Connection, catalogue_path: Path) -> list[int]:
    """Insert catalogue-only dataset rows for IDs lacking sourcedetails payloads."""

    if not catalogue_path.exists():
        return []

    existing_ids = {
        int(row[0])
        for row in conn.execute("SELECT dataset_id FROM datasets").fetchall()
        if row[0] is not None
    }
    inserted: list[int] = []

    with catalogue_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            dataset_id = _catalogue_int(row.get("dataset_id"))
            if dataset_id is None or dataset_id in existing_ids:
                continue

            name = (row.get("dataset_name") or row.get("name") or "").strip()
            if not name:
                continue

            sector = (row.get("sector") or "").strip()
            ministry = (row.get("ministry") or "").strip()
            granularity = (row.get("location_granularity") or "").strip()
            from_year = _catalogue_int(row.get("starting_year"))
            to_year = _catalogue_int(row.get("ending_year"))
            update_frequency = (row.get("frequency") or "").strip()
            n_columns = _catalogue_int(row.get("columns"))
            source_link = (row.get("url") or "").strip()
            geo_levels = _infer_geo_level(_norm_text(granularity))
            temporal_levels = _infer_temporal_level(_norm_text(update_frequency, str(from_year or ""), str(to_year or "")))

            description_parts = [part for part in (sector, granularity, f"{from_year}-{to_year}" if from_year and to_year else "", ministry) if part]
            description = "; ".join(description_parts)

            conn.execute(
                """
                INSERT INTO datasets (
                    dataset_id, name, sector, ministry, department, granularity, from_year, to_year,
                    update_frequency, n_columns, source_link, notes, geo_standard, key_dimensions,
                    geo_levels, temporal_levels, mapping_basis, description, api_key, ind_csv, dim_csv,
                    n_indicators, n_dimensions
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_id,
                    name,
                    sector,
                    ministry,
                    "",
                    granularity,
                    from_year,
                    to_year,
                    update_frequency,
                    n_columns,
                    source_link,
                    "Catalogue-only row; sourcedetails metadata was unavailable during harvest.",
                    "",
                    "",
                    geo_levels,
                    temporal_levels,
                    "",
                    description,
                    "",
                    "",
                    "",
                    0,
                    0,
                ),
            )
            conn.execute(
                """
                INSERT INTO datasets_fts (
                    dataset_id, name, notes, indicator_names, dimension_names, enrichment_text
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_id,
                    name,
                    "Catalogue-only row; sourcedetails metadata unavailable.",
                    "",
                    "",
                    " ".join(part for part in (sector, ministry, granularity, description) if part),
                ),
            )
            inserted.append(dataset_id)
            existing_ids.add(dataset_id)

    return inserted


def write_summary(conn: sqlite3.Connection) -> dict:
    n_datasets = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
    n_indicators = conn.execute("SELECT COUNT(*) FROM indicators").fetchone()[0]
    n_dimensions = conn.execute("SELECT COUNT(*) FROM dimensions").fetchone()[0]

    by_sector = {
        row[0] or "": row[1]
        for row in conn.execute(
            "SELECT COALESCE(sector, ''), COUNT(*) FROM datasets GROUP BY COALESCE(sector, '')"
        ).fetchall()
    }
    by_ministry = {
        row[0] or "": row[1]
        for row in conn.execute(
            "SELECT COALESCE(ministry, ''), COUNT(*) FROM datasets GROUP BY COALESCE(ministry, '')"
        ).fetchall()
    }

    summary = {
        "n_datasets": n_datasets,
        "n_indicators": n_indicators,
        "n_dimensions": n_dimensions,
        "by_sector": by_sector,
        "by_ministry": by_ministry,
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    args = parse_args()
    source_dir = Path(args.src)
    if not source_dir.exists():
        raise FileNotFoundError(f"Missing source directory: {source_dir}")

    db_path = Path(schema.INDEX_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    payload_files = sorted(source_dir.glob("*.json"))

    with sqlite3.connect(db_path) as conn:
        reset_schema(conn)
        inserted = 0
        for path in payload_files:
            raw = json.loads(path.read_text())
            try:
                insert_payload(conn, raw)
                inserted += 1
            except Exception as exc:
                print(f"[skip] {path.name}: {exc}")
        fallback_ids = insert_catalogue_fallbacks(conn, Path(args.catalogue))
        conn.commit()
        summary = write_summary(conn)
        if fallback_ids:
            summary["catalogue_only_dataset_ids"] = fallback_ids
            SUMMARY_PATH.write_text(json.dumps(summary, indent=2))
        conn.commit()

    print(
        f"[done] indexed={inserted} datasets={summary['n_datasets']} "
        f"indicators={summary['n_indicators']} dimensions={summary['n_dimensions']}"
    )
    if fallback_ids:
        print(f"[coverage] catalogue_only={len(fallback_ids)} ids={','.join(map(str, fallback_ids))}")


if __name__ == "__main__":
    main()
