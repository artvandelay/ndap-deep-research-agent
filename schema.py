"""Shared metadata schema and index contracts for NDAP."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

BASE = "https://loadqa.ndapapi.com"
INDEX_DB_PATH = "data/index.db"


class DatasetMeta(BaseModel):
    """Dataset-level metadata parsed from /v1/sourcedetails."""

    model_config = ConfigDict(frozen=True)

    dataset_id: int
    name: str
    sector: str = ""
    ministry: str = ""
    department: str = ""
    granularity: str = ""
    from_year: int | None = None
    to_year: int | None = None
    update_frequency: str = ""
    n_columns: int | None = None
    source_link: str = ""
    notes: str = ""
    geo_standard: str = ""
    key_dimensions: str = ""
    geo_levels: str = ""
    temporal_levels: str = ""
    mapping_basis: str = ""
    api_key: str = ""
    ind_csv: str = ""
    dim_csv: str = ""
    n_indicators: int = 0
    n_dimensions: int = 0


class IndicatorMeta(BaseModel):
    """Indicator-level metadata for one dataset."""

    model_config = ConfigDict(frozen=True)

    dataset_id: int
    ind_id: str
    display_name: str = ""
    data_type: str = ""
    units: str = ""
    scaling: str = ""
    description: str = ""
    variable_class: str = ""
    weight_variable: bool = False
    weight_scope_sector: str = ""
    weight_scope_gender: str = ""


class DimensionMeta(BaseModel):
    """Dimension-level metadata for one dataset."""

    model_config = ConfigDict(frozen=True)

    dataset_id: int
    dim_id: str
    display_name: str = ""
    data_type: str = ""
    dim_type: str = ""
    description: str = ""
    canonical_group: str = "other"
    is_key_dimension: bool = False
    geo_level: str = ""
    code_standard: str = ""


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"\d+", text)
    if not match:
        return None
    return int(match.group(0))


def _extract_dataset_id(source_row: dict[str, Any], indicators: list[dict[str, Any]]) -> int:
    for key in ("SourceID", "SourceId", "sourceid", "source_id"):
        if key in source_row and _to_int(source_row.get(key)) is not None:
            return _to_int(source_row.get(key)) or 0

    for item in indicators:
        ind_id = str(item.get("ID", ""))
        match = re.match(r"I(\d+)_", ind_id)
        if match:
            return int(match.group(1))

    raise ValueError("Unable to infer dataset_id from sourcedetails payload")


def build_openapi_url(api_key: str, ind_csv: str, dim_csv: str, pageno: int = 1) -> str:
    """Build a /v1/openapi URL using the durable dataset API key and recipe fields."""

    return (
        f"{BASE}/v1/openapi?"
        f"API_Key={quote(api_key, safe='')}&"
        f"ind={quote(ind_csv, safe=',')}&"
        f"dim={quote(dim_csv, safe=',')}&"
        f"pageno={int(pageno)}"
    )


def parse_sourcedetails(raw: dict) -> tuple[DatasetMeta, list[IndicatorMeta], list[DimensionMeta]]:
    """Parse /v1/sourcedetails response.

    Expected paths:
    - dataset row: raw["sourcedetails"]["Data"][0]
    - indicators: raw["sourcedetails"]["Data"][0]["Indicators"]["Items"]
    - dimensions: raw["sourcedetails"]["Data"][0]["Dimensions"]["Items"]
    - durable openapi key: raw["API_Key"]
    """

    source_data = raw.get("sourcedetails", {}).get("Data", [])
    if not source_data:
        raise ValueError("Missing sourcedetails.Data[0] in payload")

    row = source_data[0]
    indicators_raw = row.get("Indicators", {}).get("Items", []) or []
    dimensions_raw = row.get("Dimensions", {}).get("Items", []) or []

    dataset_id = _extract_dataset_id(row, indicators_raw)

    indicator_ids = [str(item.get("ID", "")).strip() for item in indicators_raw if str(item.get("ID", "")).strip()]
    dimension_ids = [str(item.get("ID", "")).strip() for item in dimensions_raw if str(item.get("ID", "")).strip()]

    dataset = DatasetMeta(
        dataset_id=dataset_id,
        name=str(row.get("SourceName", "")).strip(),
        sector=str(row.get("SectorName", "")).strip(),
        ministry=str(row.get("MinistryName", "")).strip(),
        department=str(row.get("DepartmentName", "")).strip(),
        granularity=str(row.get("LocalityGranularity", "")).strip(),
        from_year=_to_int(row.get("FromTimerange")),
        to_year=_to_int(row.get("ToTimerange")),
        update_frequency=str(row.get("UpdateFrequency", "")).strip(),
        n_columns=_to_int(row.get("noOfColumns")),
        source_link=str(row.get("SourceLink", "")).strip(),
        notes=str(row.get("Notes", "")).strip(),
        geo_standard="",
        key_dimensions="",
        geo_levels="",
        temporal_levels="",
        mapping_basis="",
        api_key=str(raw.get("API_Key", "")).strip(),
        ind_csv=",".join(indicator_ids),
        dim_csv=",".join(dimension_ids),
        n_indicators=len(indicator_ids),
        n_dimensions=len(dimension_ids),
    )

    indicators = [
        IndicatorMeta(
            dataset_id=dataset_id,
            ind_id=str(item.get("ID", "")).strip(),
            display_name=str(item.get("DisplayName", "")).strip(),
            data_type=str(item.get("DataType", "")).strip(),
            units=str(item.get("UnitsofMeaseure", "")).strip(),
            scaling=str(item.get("ScalingFactor", "")).strip(),
            description=str(item.get("Description", "")).strip(),
            variable_class="",
            weight_variable=False,
            weight_scope_sector="",
            weight_scope_gender="",
        )
        for item in indicators_raw
        if str(item.get("ID", "")).strip()
    ]

    dimensions = [
        DimensionMeta(
            dataset_id=dataset_id,
            dim_id=str(item.get("ID", "")).strip(),
            display_name=str(item.get("DisplayName", "")).strip(),
            data_type=str(item.get("DataType", "")).strip(),
            dim_type=str(item.get("DimensionType", "")).strip(),
            description=str(item.get("Description", "")).strip(),
            canonical_group="other",
            is_key_dimension=False,
            geo_level="",
            code_standard="",
        )
        for item in dimensions_raw
        if str(item.get("ID", "")).strip()
    ]

    return dataset, indicators, dimensions


DDL_DATASETS = """
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    ministry TEXT,
    department TEXT,
    granularity TEXT,
    from_year INTEGER,
    to_year INTEGER,
    update_frequency TEXT,
    n_columns INTEGER,
    source_link TEXT,
    notes TEXT,
    geo_standard TEXT,
    key_dimensions TEXT,
    geo_levels TEXT,
    temporal_levels TEXT,
    mapping_basis TEXT,
    description TEXT,
    api_key TEXT NOT NULL,
    ind_csv TEXT NOT NULL,
    dim_csv TEXT NOT NULL,
    n_indicators INTEGER NOT NULL,
    n_dimensions INTEGER NOT NULL
);
"""

DDL_INDICATORS = """
CREATE TABLE IF NOT EXISTS indicators (
    dataset_id INTEGER NOT NULL,
    ind_id TEXT NOT NULL,
    display_name TEXT,
    data_type TEXT,
    units TEXT,
    scaling TEXT,
    description TEXT,
    variable_class TEXT,
    weight_variable INTEGER NOT NULL DEFAULT 0,
    weight_scope_sector TEXT,
    weight_scope_gender TEXT,
    PRIMARY KEY (dataset_id, ind_id),
    FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
);
"""

DDL_DIMENSIONS = """
CREATE TABLE IF NOT EXISTS dimensions (
    dataset_id INTEGER NOT NULL,
    dim_id TEXT NOT NULL,
    display_name TEXT,
    data_type TEXT,
    dim_type TEXT,
    description TEXT,
    canonical_group TEXT,
    is_key_dimension INTEGER NOT NULL DEFAULT 0,
    geo_level TEXT,
    code_standard TEXT,
    PRIMARY KEY (dataset_id, dim_id),
    FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
);
"""

DDL_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS datasets_fts USING fts5(
    dataset_id UNINDEXED,
    name,
    notes,
    indicator_names,
    dimension_names,
    enrichment_text,
    tokenize = 'porter unicode61'
);
"""
