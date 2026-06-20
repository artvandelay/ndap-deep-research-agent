"""FastMCP server exposing NDAP metadata and download tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

import query

mcp = FastMCP("ndap")


@mcp.tool()
def search_datasets(
    q: str,
    sector: str | None = None,
    ministry: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search indexed datasets with optional sector/ministry filters."""

    return query.search_datasets(q=q, sector=sector, ministry=ministry, limit=limit)


@mcp.tool()
def get_dataset_metadata(dataset_id: int) -> dict:
    """Return dataset row plus indicators and dimensions."""

    return query.get_dataset_metadata(dataset_id=dataset_id)


@mcp.tool()
def list_sectors() -> list[dict]:
    """List sectors with dataset counts."""

    return query.list_sectors()


@mcp.tool()
def list_ministries() -> list[dict]:
    """List ministries with dataset counts."""

    return query.list_ministries()


@mcp.tool()
def download_dataset(dataset_id: int) -> str:
    """Download one dataset and return local CSV path."""

    from ndap_download import download_dataset as _download_dataset

    return _download_dataset(dataset_id=dataset_id)


if __name__ == "__main__":
    mcp.run()
