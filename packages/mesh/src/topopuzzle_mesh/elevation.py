"""The :class:`ElevationGrid` value object.

A grid is a north-up 2-D array of elevations (metres) plus everything needed to
place it in the world and attribute it correctly.  It is deliberately provider
agnostic: local GeoTIFF, terrain tiles, and synthetic fixtures all produce the
same shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np


@dataclass(frozen=True)
class Attribution:
    """Where a grid came from — carried into every export manifest."""

    provider: str
    #: Upstream DEM source names (e.g. "SRTM", "3DEP", "ETOPO1").
    sources: tuple[str, ...] = ()
    license: str = ""
    text: str = ""
    timestamp: str | None = None
    version: str | None = None

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "sources": list(self.sources),
            "license": self.license,
            "text": self.text,
            "timestamp": self.timestamp,
            "version": self.version,
        }


@dataclass(frozen=True)
class ElevationGrid:
    """A north-up elevation raster.

    ``values`` is ``[rows, cols]`` with row 0 at the northern edge.  ``bounds`` is
    ``(west, south, east, north)`` in the grid's CRS.  ``nodata_mask`` is True
    where the value is missing.
    """

    values: np.ndarray  # float32/64, shape (rows, cols), row 0 = north
    bounds: tuple[float, float, float, float]  # west, south, east, north
    crs: str  # e.g. "EPSG:4326" or "EPSG:32612"
    resolution: tuple[float, float]  # (x, y) ground units per cell
    attribution: Attribution
    nodata_mask: np.ndarray = field(default=None)  # bool, True = missing

    def __post_init__(self) -> None:
        if self.values.ndim != 2:
            raise ValueError("elevation values must be 2-D")
        if self.nodata_mask is None:
            object.__setattr__(
                self, "nodata_mask", np.zeros(self.values.shape, dtype=bool)
            )
        if self.nodata_mask.shape != self.values.shape:
            raise ValueError("nodata_mask shape must match values")

    @property
    def shape(self) -> tuple[int, int]:
        return self.values.shape

    @property
    def rows(self) -> int:
        return self.values.shape[0]

    @property
    def cols(self) -> int:
        return self.values.shape[1]

    @property
    def nodata_fraction(self) -> float:
        return float(self.nodata_mask.mean()) if self.nodata_mask.size else 0.0

    def valid_min_max(self) -> tuple[float, float]:
        """Min/max over valid cells only."""
        valid = self.values[~self.nodata_mask]
        if valid.size == 0:
            raise ValueError("grid has no valid elevation values")
        return float(valid.min()), float(valid.max())

    def with_values(self, values: np.ndarray, nodata_mask: np.ndarray | None = None) -> "ElevationGrid":
        """Return a copy with new values (and optionally a new mask)."""
        return replace(
            self,
            values=values,
            nodata_mask=self.nodata_mask if nodata_mask is None else nodata_mask,
        )
