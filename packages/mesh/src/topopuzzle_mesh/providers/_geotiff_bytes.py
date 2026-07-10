"""Decode an in-memory GeoTIFF payload into an :class:`ElevationGrid`.

Shared by the providers that fetch a raster window from a web service (USGS
3DEP, OpenTopography): they issue an HTTP request, get GeoTIFF bytes back, and
hand them here.  The service already returns exactly the requested window, so —
unlike the on-disk :class:`LocalGeoTIFFProvider` — there is no cropping to do.
"""

from __future__ import annotations

import numpy as np

from ..elevation import Attribution, ElevationGrid


def grid_from_geotiff_bytes(data: bytes, attribution: Attribution) -> ElevationGrid:
    """Read single-band elevation GeoTIFF bytes into a north-up grid."""
    from rasterio.io import MemoryFile

    with MemoryFile(data) as mem, mem.open() as ds:
        src_crs = ds.crs.to_string() if ds.crs else "EPSG:4326"
        band = ds.read(1, masked=True)
        values = np.asarray(band.filled(np.nan), dtype=np.float32)
        mask = ~np.isfinite(values)
        if hasattr(band, "mask") and band.mask is not np.ma.nomask:
            mask = mask | np.asarray(band.mask, dtype=bool)
        values = np.where(mask, 0.0, values).astype(np.float32)
        res = (abs(ds.transform.a), abs(ds.transform.e))
        b = ds.bounds  # (left, bottom, right, top)
        out_bounds = (b.left, b.bottom, b.right, b.top)

    return ElevationGrid(
        values=values,
        bounds=out_bounds,
        crs=src_crs,
        resolution=res,
        attribution=attribution,
        nodata_mask=mask,
    )


def request_dims(bounds, target_resolution_m: float, max_size: int) -> tuple[int, int]:
    """Pixel (cols, rows) for a raster-export request: honour the target
    resolution but clamp each axis to ``max_size`` pixels."""
    import math

    lat = (bounds.south + bounds.north) / 2.0
    w_m = max((bounds.east - bounds.west) * 111_320.0 * math.cos(math.radians(lat)), 1.0)
    h_m = max((bounds.north - bounds.south) * 111_320.0, 1.0)
    res = max(target_resolution_m, 1.0)
    cols = min(max_size, max(2, int(math.ceil(w_m / res))))
    rows = min(max_size, max(2, int(math.ceil(h_m / res))))
    return cols, rows
