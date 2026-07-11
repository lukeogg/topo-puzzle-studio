"""USGS 3DEP elevation provider — high-quality U.S. DEM.

Uses the 3DEP dynamic ImageServer ``exportImage`` operation, which returns a
float32 GeoTIFF for an arbitrary bbox at a requested pixel size.  Coverage is the
United States (and territories); requests outside it come back as nodata, which
we carry through.  No API key required.
"""

from __future__ import annotations

from ..config import Bounds
from ..elevation import Attribution
from ._geotiff_bytes import grid_from_geotiff_bytes, request_dims

EXPORT_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/"
    "ImageServer/exportImage"
)

_ATTRIBUTION = Attribution(
    provider="USGS 3DEP (National Map)",
    sources=("USGS 3DEP",),
    license="Public domain (U.S. Government work).",
    text=(
        "Elevation from the USGS 3D Elevation Program (3DEP), served by The "
        "National Map dynamic ImageServer. Public domain; please credit the U.S. "
        "Geological Survey. Coverage is the United States and territories."
    ),
)


class USGS3DEPProvider:
    name = "usgs-3dep"

    def __init__(self, session=None, max_size: int = 4000):
        self._session = session
        self.max_size = max_size

    def get_elevation_grid(
        self, bounds: Bounds, target_resolution_m: float = 30.0, crs: str = "EPSG:4326"
    ):
        if bounds is None:
            raise ValueError("usgs-3dep provider requires bounds")
        import requests

        sess = self._session or requests.Session()
        cols, rows = request_dims(bounds, target_resolution_m, self.max_size)
        params = {
            "bbox": f"{bounds.west},{bounds.south},{bounds.east},{bounds.north}",
            "bboxSR": "4326",
            "imageSR": "4326",
            "size": f"{cols},{rows}",
            "format": "tiff",
            "pixelType": "F32",
            "noData": "-9999",
            "interpolation": "RSP_BilinearInterpolation",
            "f": "image",
        }
        resp = sess.get(EXPORT_URL, params=params, timeout=60)
        resp.raise_for_status()
        return grid_from_geotiff_bytes(resp.content, _ATTRIBUTION)
