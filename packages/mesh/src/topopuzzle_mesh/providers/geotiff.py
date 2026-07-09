"""Local GeoTIFF elevation provider — the fully-offline MVP path."""

from __future__ import annotations

import numpy as np

from ..config import Bounds
from ..elevation import Attribution, ElevationGrid


class LocalGeoTIFFProvider:
    name = "geotiff"

    def __init__(self, path: str):
        self.path = path

    def get_elevation_grid(
        self, bounds: Bounds | None, target_resolution_m: float = 0.0, crs: str = "EPSG:4326"
    ) -> ElevationGrid:
        import rasterio
        from rasterio.windows import from_bounds as window_from_bounds

        with rasterio.open(self.path) as ds:
            src_crs = ds.crs.to_string() if ds.crs else "EPSG:4326"
            if bounds is not None:
                # Reproject the request bbox into the raster CRS if needed.
                w, s, e, n = bounds.west, bounds.south, bounds.east, bounds.north
                if ds.crs and ds.crs.to_epsg() != 4326:
                    from pyproj import Transformer

                    tr = Transformer.from_crs("EPSG:4326", src_crs, always_xy=True)
                    xs, ys = tr.transform([w, e, w, e], [s, s, n, n])
                    w, e, s, n = min(xs), max(xs), min(ys), max(ys)
                window = window_from_bounds(w, s, e, n, ds.transform)
                data = ds.read(1, window=window, masked=True)
                win_transform = ds.window_transform(window)
                from rasterio.transform import array_bounds

                b = array_bounds(data.shape[0], data.shape[1], win_transform)
                out_bounds = (b[0], b[1], b[2], b[3])
            else:
                data = ds.read(1, masked=True)
                out_bounds = tuple(ds.bounds)

            values = np.asarray(data.filled(np.nan), dtype=np.float32)
            mask = ~np.isfinite(values)
            if hasattr(data, "mask") and data.mask is not np.ma.nomask:
                mask = mask | np.asarray(data.mask, dtype=bool)
            values = np.where(mask, 0.0, values).astype(np.float32)
            res = (abs(ds.transform.a), abs(ds.transform.e))

        return ElevationGrid(
            values=values,
            bounds=out_bounds,
            crs=src_crs,
            resolution=res,
            attribution=Attribution(
                provider="Local GeoTIFF",
                sources=("user-supplied GeoTIFF",),
                license="user-supplied",
                text=f"Loaded from {self.path}",
            ),
            nodata_mask=mask,
        )
