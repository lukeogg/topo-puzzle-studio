"""OpenTopoData elevation provider — small-area / preview / self-hosted fallback.

OpenTopoData is a *point-lookup* API: you ask for the elevation at a list of
lat/lon points and it samples its chosen dataset.  There is no tile or window
download, so building a dense mesh grid means sampling one point per cell.  The
public instance (``api.opentopodata.org``) caps a request at 100 locations, one
call per second, 1000 calls per day, so we deliberately **cap the total sample
count** and reduce the grid resolution to fit.  Point a self-hosted instance at
``base_url`` and raise ``max_points`` to lift that ceiling.

The response elevation is ``null`` over ocean / outside a dataset's coverage; we
carry those through as nodata so downstream fill/normalise behaves.
"""

from __future__ import annotations

import math

import numpy as np

from ..config import Bounds
from ..elevation import Attribution, ElevationGrid

#: Public instance URL; override with a self-hosted base for larger requests.
DEFAULT_BASE_URL = "https://api.opentopodata.org"
#: Public instance hard limit per request.
PUBLIC_BATCH = 100

# Per-dataset licence notes for the datasets the public instance exposes.  Only a
# short human-facing summary — the canonical terms live at the dataset source.
_DATASET_LICENSE = {
    "aster30m": "ASTER GDEM v3 — METI/NASA, free use with attribution.",
    "srtm30m": "NASA SRTM 1 arc-second — public domain.",
    "srtm90m": "NASA SRTM 3 arc-second — public domain.",
    "nzdem8m": "LINZ NZ 8 m DEM — CC BY 4.0.",
    "ned10m": "USGS NED 1/3 arc-second — public domain (US only).",
    "eudem25m": "Copernicus EU-DEM 25 m — free use with attribution.",
    "mapzen": "Mapzen/Tilezen terrain (mixed upstream) — public domain / mixed.",
    "etopo1": "NOAA ETOPO1 global relief — public domain.",
    "gebco2020": "GEBCO 2020 bathymetry/topography — free use with attribution.",
}


def _sample_dims(bounds: Bounds, target_resolution_m: float, max_points: int) -> tuple[int, int]:
    """Grid (rows, cols) that honours the target resolution but never exceeds
    ``max_points`` total sample points, preserving geographic aspect ratio."""
    lat = (bounds.south + bounds.north) / 2.0
    w_m = max((bounds.east - bounds.west) * 111_320.0 * math.cos(math.radians(lat)), 1.0)
    h_m = max((bounds.north - bounds.south) * 111_320.0, 1.0)
    res = max(target_resolution_m, 1.0)
    cols = max(2, int(math.ceil(w_m / res)) + 1)
    rows = max(2, int(math.ceil(h_m / res)) + 1)
    if cols * rows > max_points:
        scale = math.sqrt(max_points / (cols * rows))
        cols = max(2, int(cols * scale))
        rows = max(2, int(rows * scale))
        while cols * rows > max_points and (cols > 2 or rows > 2):
            if cols >= rows and cols > 2:
                cols -= 1
            elif rows > 2:
                rows -= 1
            else:
                break
    return rows, cols


class OpenTopoDataProvider:
    name = "opentopodata"

    def __init__(
        self,
        dataset: str = "aster30m",
        *,
        base_url: str = DEFAULT_BASE_URL,
        session=None,
        max_points: int = PUBLIC_BATCH,
        batch_size: int = PUBLIC_BATCH,
    ):
        self.dataset = dataset
        self.base_url = base_url.rstrip("/")
        self._session = session
        # Never sample more points than a single public request allows unless a
        # caller (self-host) explicitly raises the cap.
        self.max_points = max(4, max_points)
        self.batch_size = max(1, min(batch_size, PUBLIC_BATCH))

    def _attribution(self) -> Attribution:
        selfhost = self.base_url != DEFAULT_BASE_URL
        note = _DATASET_LICENSE.get(self.dataset, "See the dataset's own licence terms.")
        return Attribution(
            provider=f"OpenTopoData ({self.dataset})"
            + (" [self-hosted]" if selfhost else ""),
            sources=(self.dataset,),
            license=note,
            text=(
                f"Elevation sampled from OpenTopoData dataset '{self.dataset}' via "
                f"{self.base_url}. {note} OpenTopoData is a point-lookup API; grids "
                "are sampled at capped density on the public instance."
            ),
        )

    def get_elevation_grid(
        self, bounds: Bounds, target_resolution_m: float = 90.0, crs: str = "EPSG:4326"
    ) -> ElevationGrid:
        if bounds is None:
            raise ValueError("opentopodata provider requires bounds")
        import requests

        sess = self._session or requests.Session()
        rows, cols = _sample_dims(bounds, target_resolution_m, self.max_points)

        # North-up sample lattice: row 0 = north edge, cell centres across bounds.
        lats = np.linspace(bounds.north, bounds.south, rows)
        lons = np.linspace(bounds.west, bounds.east, cols)
        lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
        flat = np.column_stack([lat_grid.ravel(), lon_grid.ravel()])

        elevations: list[float | None] = []
        for start in range(0, flat.shape[0], self.batch_size):
            chunk = flat[start : start + self.batch_size]
            locations = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in chunk)
            url = f"{self.base_url}/v1/{self.dataset}"
            resp = sess.get(url, params={"locations": locations}, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") not in (None, "OK"):
                raise RuntimeError(f"OpenTopoData error: {payload.get('error', payload)}")
            for result in payload.get("results", []):
                elevations.append(result.get("elevation"))

        if len(elevations) != rows * cols:
            raise RuntimeError(
                f"OpenTopoData returned {len(elevations)} elevations, expected {rows * cols}"
            )

        arr = np.array(
            [np.nan if e is None else float(e) for e in elevations], dtype=np.float32
        ).reshape(rows, cols)
        mask = ~np.isfinite(arr)
        values = np.where(mask, 0.0, arr).astype(np.float32)

        res = (
            (bounds.east - bounds.west) / max(cols - 1, 1),
            (bounds.north - bounds.south) / max(rows - 1, 1),
        )
        return ElevationGrid(
            values=values,
            bounds=(bounds.west, bounds.south, bounds.east, bounds.north),
            crs="EPSG:4326",
            resolution=res,
            attribution=self._attribution(),
            nodata_mask=mask,
        )
