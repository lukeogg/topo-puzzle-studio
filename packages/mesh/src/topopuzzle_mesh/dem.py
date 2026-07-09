"""DEM raster processing: reprojection to true metres, resampling, gap filling,
smoothing, water flattening, and normalization.

All functions are pure and deterministic so the geometry pipeline is reproducible.
The mesh must be built in a projected CRS (metres) so that millimetre dimensions
are truthful; :func:`reproject_to_utm` handles that.
"""

from __future__ import annotations

import numpy as np
from pyproj import Transformer
from scipy import ndimage

from .elevation import Attribution, ElevationGrid

# Sanity bounds on real-world elevations (metres): Challenger Deep to Everest,
# with headroom.  Anything outside is a sentinel or a decoding bug, not terrain.
ELEVATION_MIN_M = -12_000.0
ELEVATION_MAX_M = 9_000.0

# --------------------------------------------------------------------------- #
# Projection
# --------------------------------------------------------------------------- #


def utm_epsg_for_lonlat(lon: float, lat: float) -> int:
    """Return the EPSG code of the UTM zone containing ``(lon, lat)``."""
    zone = int((lon + 180.0) // 6.0) + 1
    zone = max(1, min(60, zone))
    return (32600 if lat >= 0 else 32700) + zone


def _is_geographic(crs: str) -> bool:
    return crs.upper() in ("EPSG:4326", "WGS84", "EPSG:4979")


def reproject_to_utm(grid: ElevationGrid) -> ElevationGrid:
    """Warp a geographic grid into its local UTM zone so cells are square metres.

    A grid already in a projected CRS is returned unchanged.  Uses rasterio's
    warp for correctness; the destination resolution matches the source ground
    resolution so no detail is invented.
    """
    if not _is_geographic(grid.crs):
        return grid

    from rasterio.transform import array_bounds, from_bounds
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    west, south, east, north = grid.bounds
    lon_c, lat_c = (west + east) / 2.0, (south + north) / 2.0
    dst_epsg = utm_epsg_for_lonlat(lon_c, lat_c)
    dst_crs = f"EPSG:{dst_epsg}"

    src_transform = from_bounds(west, south, east, north, grid.cols, grid.rows)
    dst_transform, dst_w, dst_h = calculate_default_transform(
        grid.crs, dst_crs, grid.cols, grid.rows, west, south, east, north
    )

    src = np.ascontiguousarray(grid.values, dtype=np.float32)
    dst = np.empty((dst_h, dst_w), dtype=np.float32)
    nodata_val = np.float32(-1e30)
    reproject(
        source=src,
        destination=dst,
        src_transform=src_transform,
        src_crs=grid.crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        src_nodata=None,
        dst_nodata=float(nodata_val),
        resampling=Resampling.bilinear,
    )
    # Carry the nodata mask through the same warp.
    src_mask = grid.nodata_mask.astype(np.float32)
    dst_mask = np.empty((dst_h, dst_w), dtype=np.float32)
    reproject(
        source=src_mask,
        destination=dst_mask,
        src_transform=src_transform,
        src_crs=grid.crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.nearest,
    )
    mask = (dst_mask > 0.5) | (dst == nodata_val) | ~np.isfinite(dst)
    # Never leave the sentinel in `values`: a UTM warp of a lon/lat quad leaves
    # unmapped corner pixels, and -1e30 masquerades as a real elevation to any
    # downstream min()/interpolation.  NaN cannot.
    dst[mask] = np.nan

    b = array_bounds(dst_h, dst_w, dst_transform)  # (west, south, east, north)
    res = (abs(dst_transform.a), abs(dst_transform.e))
    return ElevationGrid(
        values=dst,
        bounds=(b[0], b[1], b[2], b[3]),
        crs=dst_crs,
        resolution=res,
        attribution=grid.attribution,
        nodata_mask=mask,
    )


def ground_extent_m(grid: ElevationGrid) -> tuple[float, float]:
    """Return the (width, height) of the grid footprint in metres.

    For a projected grid this is exact; for a geographic grid it is computed by
    transforming the corner coordinates through the local UTM zone.
    """
    west, south, east, north = grid.bounds
    if not _is_geographic(grid.crs):
        return (east - west, north - south)
    epsg = utm_epsg_for_lonlat((west + east) / 2, (south + north) / 2)
    tr = Transformer.from_crs(grid.crs, f"EPSG:{epsg}", always_xy=True)
    xs, ys = tr.transform([west, east, west, east], [south, south, north, north])
    return (max(xs) - min(xs), max(ys) - min(ys))


# --------------------------------------------------------------------------- #
# Resampling
# --------------------------------------------------------------------------- #


def resample_to_max(grid: ElevationGrid, max_grid: int) -> ElevationGrid:
    """Downsample so the longest side has at most ``max_grid`` cells.

    Aspect ratio is preserved.  Grids already small enough are returned as-is.
    """
    rows, cols = grid.shape
    longest = max(rows, cols)
    if longest <= max_grid:
        return grid
    scale = max_grid / longest
    new_rows = max(2, round(rows * scale))
    new_cols = max(2, round(cols * scale))
    zoom = (new_rows / rows, new_cols / cols)
    # Fill nodata before zoom so it doesn't smear: the bilinear zoom below would
    # bleed missing cells into valid neighbours, while the nearest-resampled mask
    # would not grow to cover them.
    if grid.nodata_fraction > 0.0:
        grid, _ = fill_nodata(grid)
    values = ndimage.zoom(grid.values, zoom, order=1)
    mask = ndimage.zoom(grid.nodata_mask.astype(np.float32), zoom, order=0) > 0.5
    west, south, east, north = grid.bounds
    res = ((east - west) / new_cols, (north - south) / new_rows)
    return ElevationGrid(
        values=values.astype(np.float32),
        bounds=grid.bounds,
        crs=grid.crs,
        resolution=res,
        attribution=grid.attribution,
        nodata_mask=mask,
    )


# --------------------------------------------------------------------------- #
# Gap filling / smoothing / water
# --------------------------------------------------------------------------- #


def fill_nodata(grid: ElevationGrid) -> tuple[ElevationGrid, float]:
    """Interpolate missing cells from nearest valid neighbours.

    Returns the filled grid and the fraction of cells that were missing.
    """
    frac = grid.nodata_fraction
    if frac == 0.0:
        return grid, 0.0
    values = grid.values.copy()
    mask = grid.nodata_mask
    # Nearest-valid via distance transform indices — cheap and robust.
    idx = ndimage.distance_transform_edt(
        mask, return_distances=False, return_indices=True
    )
    values[mask] = values[tuple(idx[:, mask])]
    filled = grid.with_values(values.astype(np.float32), np.zeros_like(mask))
    return filled, frac


def gaussian_smooth(grid: ElevationGrid, sigma: float) -> ElevationGrid:
    """Gaussian-smooth elevations in cell units.  ``sigma <= 0`` is a no-op."""
    if sigma <= 0:
        return grid
    smoothed = ndimage.gaussian_filter(grid.values, sigma=sigma, mode="nearest")
    return grid.with_values(smoothed.astype(np.float32))


def flatten_water(grid: ElevationGrid, threshold_m: float) -> ElevationGrid:
    """Clamp all elevations at or below ``threshold_m`` up to the threshold,
    producing a flat water surface in real-world metres."""
    values = np.maximum(grid.values, threshold_m).astype(np.float32)
    return grid.with_values(values)


# --------------------------------------------------------------------------- #
# Normalization  (metres -> model Z, with base and exaggeration)
# --------------------------------------------------------------------------- #


def normalize_z(
    values_m: np.ndarray,
    *,
    horizontal_scale: float,
    z_exaggeration: float,
    base_mm: float,
) -> np.ndarray:
    """Convert real-world elevations (metres) to model Z (mm).

    The minimum terrain elevation is placed exactly at the top of the base slab,
    then relief is scaled by the same horizontal mm-per-metre factor as the
    footprint and multiplied by the vertical exaggeration.  This keeps a 1x model
    true to life and makes exaggeration a pure multiplier on top of that.
    """
    # A single leftover nodata sentinel would become the reference min and blow
    # the relief up by ~30 orders of magnitude, silently yielding a mesh that
    # every downstream CSG returns empty for.  Refuse it loudly instead.
    if not np.isfinite(values_m).all():
        raise ValueError("elevation grid contains non-finite values — fill nodata first")
    lo, hi = float(values_m.min()), float(values_m.max())
    if lo < ELEVATION_MIN_M or hi > ELEVATION_MAX_M:
        raise ValueError(
            f"elevation range {lo:.1f}..{hi:.1f} m is outside the plausible "
            f"{ELEVATION_MIN_M:.0f}..{ELEVATION_MAX_M:.0f} m — likely an unfilled "
            "nodata sentinel in the grid"
        )
    relief = values_m - lo
    z = base_mm + relief * horizontal_scale * z_exaggeration
    return z.astype(np.float64)


# --------------------------------------------------------------------------- #
# Synthetic fixtures (no network) — used by tests and examples
# --------------------------------------------------------------------------- #


def _grid(values: np.ndarray, mask: np.ndarray | None = None) -> ElevationGrid:
    rows, cols = values.shape
    # A small patch of Montana, in degrees — just needs to be plausible lon/lat.
    bounds = (-111.90, 48.50, -111.70, 48.70)
    res = ((bounds[2] - bounds[0]) / cols, (bounds[3] - bounds[1]) / rows)
    return ElevationGrid(
        values=values.astype(np.float32),
        bounds=bounds,
        crs="EPSG:4326",
        resolution=res,
        attribution=Attribution(provider="synthetic", sources=("fixture",), text="Synthetic DEM"),
        nodata_mask=mask,
    )


def fixture(kind: str, n: int = 64) -> ElevationGrid:
    """Deterministic synthetic DEMs for tests: ``ramp``, ``hill``, ``flat``,
    ``coastal``, ``nodata``."""
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    xn, yn = xx / (n - 1), yy / (n - 1)
    if kind == "ramp":
        return _grid(100.0 + 900.0 * xn)
    if kind == "hill":
        r2 = (xn - 0.5) ** 2 + (yn - 0.5) ** 2
        return _grid(500.0 + 800.0 * np.exp(-r2 / 0.05))
    if kind == "flat":
        return _grid(np.full((n, n), 250.0))
    if kind == "coastal":
        # Sea on the west half, rising land to the east.
        land = np.clip((xn - 0.4) * 1500.0, -50.0, None)
        return _grid(land)
    if kind == "nodata":
        vals = 500.0 + 400.0 * np.exp(-(((xn - 0.5) ** 2 + (yn - 0.5) ** 2) / 0.08))
        mask = np.zeros((n, n), dtype=bool)
        mask[n // 3 : n // 3 + n // 8, n // 3 : n // 3 + n // 8] = True
        return _grid(vals, mask)
    raise ValueError(f"unknown fixture kind: {kind!r}")
