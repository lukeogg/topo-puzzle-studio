"""Provider registry."""

from __future__ import annotations

from .base import ElevationProvider
from .geotiff import LocalGeoTIFFProvider
from .terrain_tiles import TerrainTilesProvider

__all__ = ["ElevationProvider", "LocalGeoTIFFProvider", "TerrainTilesProvider", "get_provider"]


def get_provider(name: str, *, geotiff_path: str | None = None) -> ElevationProvider:
    """Construct a provider by name (``geotiff`` requires ``geotiff_path``)."""
    if name == "geotiff":
        if not geotiff_path:
            raise ValueError("geotiff provider requires geotiff_path")
        return LocalGeoTIFFProvider(geotiff_path)
    if name == "terrain-tiles":
        return TerrainTilesProvider()
    raise ValueError(f"unknown provider: {name!r}")
