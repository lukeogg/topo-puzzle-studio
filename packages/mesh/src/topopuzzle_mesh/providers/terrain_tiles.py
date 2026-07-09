"""AWS/Mapzen Terrain Tiles provider (terrarium PNG).

No API key, global coverage — the online default.  Elevation is decoded from the
RGB terrarium encoding.  Attribution preserves the upstream Tilezen/Mapzen DEM
sources (SRTM, 3DEP, ETOPO1, …), not merely "AWS Terrain Tiles".
"""

from __future__ import annotations

import io
import math

import numpy as np

from ..config import Bounds
from ..elevation import Attribution, ElevationGrid

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TILE_SIZE = 256

_ATTRIBUTION = Attribution(
    provider="AWS Terrain Tiles (Tilezen/Mapzen terrarium)",
    sources=("SRTM", "USGS 3DEP", "ETOPO1", "GMTED2010", "and other national DEMs"),
    license="Public domain / mixed — see https://github.com/tilezen/joerd/blob/master/docs/attribution.md",
    text=(
        "Elevation tiles courtesy of Mapzen/Tilezen, served from AWS Open Data. "
        "Upstream sources include SRTM, USGS 3DEP, ETOPO1, GMTED2010, and various "
        "national datasets; attribution requirements vary by source and region."
    ),
)


def _deg2num(lat: float, lon: float, z: int) -> tuple[float, float]:
    lat_r = math.radians(lat)
    n = 2.0**z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return x, y


def _num2deg(x: float, y: float, z: int) -> tuple[float, float]:
    n = 2.0**z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def _zoom_for_resolution(bounds: Bounds, target_resolution_m: float) -> int:
    lat = (bounds.south + bounds.north) / 2.0
    # Ground metres per tile pixel at zoom z near the equator, scaled by cos(lat).
    for z in range(0, 15):
        mpp = 156543.03 * math.cos(math.radians(lat)) / (2**z)
        if mpp <= max(target_resolution_m, 5.0):
            return z
    return 14


class TerrainTilesProvider:
    name = "terrain-tiles"

    def __init__(self, session=None, max_tiles: int = 64):
        self._session = session
        self.max_tiles = max_tiles

    def get_elevation_grid(
        self, bounds: Bounds, target_resolution_m: float = 90.0, crs: str = "EPSG:4326"
    ) -> ElevationGrid:
        import requests
        from PIL import Image

        sess = self._session or requests.Session()
        z = _zoom_for_resolution(bounds, target_resolution_m)

        x0f, y0f = _deg2num(bounds.north, bounds.west, z)  # top-left
        x1f, y1f = _deg2num(bounds.south, bounds.east, z)  # bottom-right
        x0, x1 = int(math.floor(x0f)), int(math.floor(x1f))
        y0, y1 = int(math.floor(y0f)), int(math.floor(y1f))
        nx, ny = x1 - x0 + 1, y1 - y0 + 1
        while nx * ny > self.max_tiles and z > 0:
            z -= 1
            x0f, y0f = _deg2num(bounds.north, bounds.west, z)
            x1f, y1f = _deg2num(bounds.south, bounds.east, z)
            x0, x1 = int(math.floor(x0f)), int(math.floor(x1f))
            y0, y1 = int(math.floor(y0f)), int(math.floor(y1f))
            nx, ny = x1 - x0 + 1, y1 - y0 + 1

        mosaic = np.zeros((ny * TILE_SIZE, nx * TILE_SIZE), dtype=np.float32)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                url = TILE_URL.format(z=z, x=tx, y=ty)
                resp = sess.get(url, timeout=30)
                resp.raise_for_status()
                img = np.asarray(Image.open(io.BytesIO(resp.content)).convert("RGB"), dtype=np.float32)
                elev = (img[..., 0] * 256.0 + img[..., 1] + img[..., 2] / 256.0) - 32768.0
                oy, ox = (ty - y0) * TILE_SIZE, (tx - x0) * TILE_SIZE
                mosaic[oy : oy + TILE_SIZE, ox : ox + TILE_SIZE] = elev

        # Crop the mosaic to the requested bounds (fractional tile offsets).
        top = (y0f - y0) * TILE_SIZE
        left = (x0f - x0) * TILE_SIZE
        bottom = (y1f - y0) * TILE_SIZE
        right = (x1f - x0) * TILE_SIZE
        r0, r1 = int(round(top)), int(round(bottom))
        c0, c1 = int(round(left)), int(round(right))
        r1, c1 = max(r1, r0 + 2), max(c1, c0 + 2)
        crop = mosaic[r0:r1, c0:c1]

        west_deg = bounds.west
        east_deg = bounds.east
        res = ((east_deg - west_deg) / crop.shape[1], (bounds.north - bounds.south) / crop.shape[0])
        return ElevationGrid(
            values=crop.astype(np.float32),
            bounds=(bounds.west, bounds.south, bounds.east, bounds.north),
            crs="EPSG:4326",
            resolution=res,
            attribution=_ATTRIBUTION,
            nodata_mask=np.zeros(crop.shape, dtype=bool),
        )
