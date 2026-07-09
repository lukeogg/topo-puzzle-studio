"""Elevation provider interface.

Every provider maps a request for a bounding box + target resolution to a single
:class:`~topopuzzle_mesh.elevation.ElevationGrid`, carrying attribution so the
export manifest can always credit the upstream DEM source.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..config import Bounds
from ..elevation import ElevationGrid


@runtime_checkable
class ElevationProvider(Protocol):
    name: str

    def get_elevation_grid(
        self, bounds: Bounds, target_resolution_m: float, crs: str = "EPSG:4326"
    ) -> ElevationGrid: ...
