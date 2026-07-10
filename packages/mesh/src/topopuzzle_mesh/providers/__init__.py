"""Provider registry."""

from __future__ import annotations

from .base import ElevationProvider
from .geotiff import LocalGeoTIFFProvider
from .opentopodata import OpenTopoDataProvider
from .opentopography import OpenTopographyProvider
from .terrain_tiles import TerrainTilesProvider
from .usgs_3dep import USGS3DEPProvider

__all__ = [
    "ElevationProvider",
    "LocalGeoTIFFProvider",
    "OpenTopoDataProvider",
    "OpenTopographyProvider",
    "TerrainTilesProvider",
    "USGS3DEPProvider",
    "get_provider",
]


def get_provider(name: str, *, geotiff_path: str | None = None) -> ElevationProvider:
    """Construct a provider by name (``geotiff`` requires ``geotiff_path``)."""
    if name == "geotiff":
        if not geotiff_path:
            raise ValueError("geotiff provider requires geotiff_path")
        return LocalGeoTIFFProvider(geotiff_path)
    if name == "terrain-tiles":
        return TerrainTilesProvider()
    if name == "opentopodata":
        return OpenTopoDataProvider()
    if name == "usgs-3dep":
        return USGS3DEPProvider()
    if name == "opentopography":
        return OpenTopographyProvider()
    raise ValueError(f"unknown provider: {name!r}")
