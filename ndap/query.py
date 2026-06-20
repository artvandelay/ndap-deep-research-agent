"""Query layer over NDAP metadata index."""

from __future__ import annotations

import sqlite3
from typing import Any

import schema


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(schema.INDEX_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def search_datasets(
    q: str,
    sector: str | None = None,
    ministry: str | None = None,
    limit: int = 20,
) -> list[dict]:
    safe_limit = max(1, min(limit, 200))
    query_text = q.strip()

    where_clauses = []
    params: list[Any] = []

    if sector:
        where_clauses.append("d.sector = ?")
        params.append(sector)
    if ministry:
        where_clauses.append("d.ministry = ?")
        params.append(ministry)

    with _connect() as conn:
        if query_text:
            sql = """
                SELECT
                    d.dataset_id AS id,
                    d.name,
                    d.description,
                    d.sector,
                    d.ministry,
                    d.n_columns,
                    d.from_year,
                    d.to_year,
                    d.geo_standard,
                    d.key_dimensions,
                    d.geo_levels,
                    d.temporal_levels,
                    d.mapping_basis
                FROM datasets_fts f
                JOIN datasets d ON d.dataset_id = CAST(f.dataset_id AS INTEGER)
                WHERE f.datasets_fts MATCH ?
            """
            params = [query_text] + params
            if where_clauses:
                sql += " AND " + " AND ".join(where_clauses)
            sql += " ORDER BY bm25(datasets_fts), d.dataset_id LIMIT ?"
            params.append(safe_limit)
        else:
            sql = """
                SELECT
                    d.dataset_id AS id,
                    d.name,
                    d.description,
                    d.sector,
                    d.ministry,
                    d.n_columns,
                    d.from_year,
                    d.to_year,
                    d.geo_standard,
                    d.key_dimensions,
                    d.geo_levels,
                    d.temporal_levels,
                    d.mapping_basis
                FROM datasets d
            """
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
            sql += " ORDER BY d.name LIMIT ?"
            params.append(safe_limit)

        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


def get_dataset_metadata(dataset_id: int) -> dict:
    with _connect() as conn:
        dataset_row = conn.execute(
            "SELECT * FROM datasets WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        dataset = _row_to_dict(dataset_row)
        if not dataset:
            raise ValueError(f"Dataset not found: {dataset_id}")

        indicators = conn.execute(
            """
            SELECT
                ind_id,
                display_name,
                data_type,
                units,
                scaling,
                description,
                variable_class,
                weight_variable,
                weight_scope_sector,
                weight_scope_gender
            FROM indicators
            WHERE dataset_id = ?
            ORDER BY ind_id
            """,
            (dataset_id,),
        ).fetchall()
        dimensions = conn.execute(
            """
            SELECT
                dim_id,
                display_name,
                data_type,
                dim_type,
                description,
                canonical_group,
                is_key_dimension,
                geo_level,
                code_standard
            FROM dimensions
            WHERE dataset_id = ?
            ORDER BY dim_id
            """,
            (dataset_id,),
        ).fetchall()

    return {
        "dataset": dataset,
        "indicators": [dict(row) for row in indicators],
        "dimensions": [dict(row) for row in dimensions],
    }


def list_sectors() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT sector, COUNT(*) AS count
            FROM datasets
            GROUP BY sector
            ORDER BY count DESC, sector ASC
            """
        ).fetchall()
    return [{"sector": row["sector"], "count": row["count"]} for row in rows]


def list_ministries() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT ministry, COUNT(*) AS count
            FROM datasets
            GROUP BY ministry
            ORDER BY count DESC, ministry ASC
            """
        ).fetchall()
    return [{"ministry": row["ministry"], "count": row["count"]} for row in rows]
