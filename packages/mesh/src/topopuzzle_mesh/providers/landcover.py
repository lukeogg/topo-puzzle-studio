"""Land-cover providers (Tier-4).

A land-cover grid is a categorical raster: each cell holds a *class code* (tree,
grass, water, built, …) rather than an elevation.  Two ways in, same
:class:`LandCoverGrid` out:

* :class:`LocalLandCoverProvider` — a user-supplied classified GeoTIFF (offline).
* :class:`WorldCoverProvider` — ESA WorldCover 10 m global COGs on AWS open data
  (no key).  Network/best-effort; reads the covering 3° tile windowed to bounds.

ESA WorldCover is CC BY 4.0 — attribution flows into the export manifest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..config import Bounds
from ..elevation import Attribution

# ESA WorldCover v200 class codes → (name, representative hex).
WORLDCOVER_LEGEND = {
    10: ("tree cover", "#0a6b2d"),
    20: ("shrubland", "#c8a24a"),
    30: ("grassland", "#f7e08a"),
    40: ("cropland", "#f0b23c"),
    50: ("built-up", "#c4281b"),
    60: ("bare / sparse", "#b4b4b4"),
    70: ("snow / ice", "#f0f0f0"),
    80: ("water", "#2f6fb0"),
    90: ("wetland", "#6fc0c0"),
    95: ("mangrove", "#0a8f6f"),
    100: ("moss / lichen", "#d0c0a0"),
}


@dataclass(frozen=True)
class LandCoverGrid:
    """A north-up categorical raster of land-cover class codes."""

    classes: np.ndarray  # int (rows, cols), row 0 = north
    bounds: tuple[float, float, float, float]  # west, south, east, north
    crs: str
    resolution: tuple[float, float]
    attribution: Attribution
    #: code -> (name, hex)
    legend: dict = field(default_factory=lambda: dict(WORLDCOVER_LEGEND))
    nodata: int = 0

    @property
    def shape(self):
        return self.classes.shape


def _read_class_geotiff(path_or_url: str, attribution: Attribution, legend: dict, *, bounds=None) -> LandCoverGrid:
    import rasterio
    from rasterio.windows import from_bounds as window_from_bounds

    with rasterio.open(path_or_url) as ds:
        src_crs = ds.crs.to_string() if ds.crs else "EPSG:4326"
        nodata = int(ds.nodata) if ds.nodata is not None else 0
        if bounds is not None:
            w, s, e, n = bounds.west, bounds.south, bounds.east, bounds.north
            if ds.crs and ds.crs.to_epsg() != 4326:
                from pyproj import Transformer

                tr = Transformer.from_crs("EPSG:4326", src_crs, always_xy=True)
                xs, ys = tr.transform([w, e, w, e], [s, s, n, n])
                w, e, s, n = min(xs), max(xs), min(ys), max(ys)
            window = window_from_bounds(w, s, e, n, ds.transform)
            data = ds.read(1, window=window, boundless=True, fill_value=nodata)
            from rasterio.transform import array_bounds

            wt = ds.window_transform(window)
            b = array_bounds(data.shape[0], data.shape[1], wt)
            out_bounds = (b[0], b[1], b[2], b[3])
        else:
            data = ds.read(1)
            out_bounds = tuple(ds.bounds)
        res = (abs(ds.transform.a), abs(ds.transform.e))

    return LandCoverGrid(
        classes=np.asarray(data, dtype=np.int32),
        bounds=out_bounds,
        crs=src_crs,
        resolution=res,
        attribution=attribution,
        legend=legend,
        nodata=nodata,
    )


class LocalLandCoverProvider:
    name = "landcover-local"

    def __init__(self, path: str, legend: dict | None = None):
        self.path = path
        self.legend = legend or dict(WORLDCOVER_LEGEND)

    def get_landcover_grid(self, bounds: Bounds | None = None, target_resolution_m: float = 0.0, crs: str = "EPSG:4326") -> LandCoverGrid:
        attribution = Attribution(
            provider="Local classified raster",
            sources=("user-supplied land-cover raster",),
            license="user-supplied",
            text=f"Loaded from {self.path}",
        )
        return _read_class_geotiff(self.path, attribution, self.legend, bounds=bounds)


_WC_ATTRIBUTION = Attribution(
    provider="ESA WorldCover 10 m v200 (2021)",
    sources=("ESA WorldCover",),
    license="CC BY 4.0",
    text=(
        "Land cover © ESA WorldCover project 2021 / Contains modified Copernicus "
        "Sentinel data, served from AWS Open Data. Licensed CC BY 4.0."
    ),
)


def _worldcover_tile(lat: float, lon: float) -> str:
    """Name of the 3°×3° WorldCover tile whose SW corner contains (lat, lon)."""
    tlat = int(math.floor(lat / 3.0) * 3)
    tlon = int(math.floor(lon / 3.0) * 3)
    ns = f"N{tlat:02d}" if tlat >= 0 else f"S{-tlat:02d}"
    ew = f"E{tlon:03d}" if tlon >= 0 else f"W{-tlon:03d}"
    return f"{ns}{ew}"


class WorldCoverProvider:
    name = "worldcover"

    BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or self.BASE).rstrip("/")

    def tile_url(self, bounds: Bounds) -> str:
        clon, clat = bounds.center
        tile = _worldcover_tile(clat, clon)
        return f"/vsicurl/{self.base_url}/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"

    def get_landcover_grid(self, bounds: Bounds, target_resolution_m: float = 10.0, crs: str = "EPSG:4326") -> LandCoverGrid:
        if bounds is None:
            raise ValueError("worldcover provider requires bounds")
        return _read_class_geotiff(
            self.tile_url(bounds), _WC_ATTRIBUTION, dict(WORLDCOVER_LEGEND), bounds=bounds
        )
