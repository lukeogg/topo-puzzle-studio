"""DEM processing math: resample, fill, smoothing, normalization, exaggeration."""

from __future__ import annotations

import numpy as np

from topopuzzle_mesh import dem


def test_resample_caps_long_side():
    g = dem.fixture("hill", 300)
    r = dem.resample_to_max(g, 100)
    assert max(r.shape) == 100
    # aspect preserved (square in, square out)
    assert r.shape[0] == r.shape[1]


def test_resample_noop_when_small():
    g = dem.fixture("hill", 40)
    r = dem.resample_to_max(g, 100)
    assert r.shape == g.shape


def test_fill_nodata_removes_mask_and_reports_fraction():
    g = dem.fixture("nodata", 64)
    frac_before = g.nodata_fraction
    filled, reported = dem.fill_nodata(g)
    assert reported == frac_before > 0
    assert filled.nodata_fraction == 0.0
    assert np.isfinite(filled.values).all()


def test_reproject_leaves_no_sentinel_in_values():
    """Warping a lon/lat quad into UTM leaves unmapped corners; they must be
    masked and NaN, never a finite sentinel that can pass for an elevation."""
    g = dem.fixture("hill", 64)
    u = dem.reproject_to_utm(g)
    assert u.nodata_fraction > 0.0  # rotated quad => unmapped corners
    assert np.isnan(u.values[u.nodata_mask]).all()
    valid = u.values[~u.nodata_mask]
    assert valid.min() > dem.ELEVATION_MIN_M and valid.max() < dem.ELEVATION_MAX_M


def test_resample_does_not_smear_nodata_into_valid_cells():
    """A bilinear downsample must not bleed missing cells into real terrain."""
    g = dem.reproject_to_utm(dem.fixture("hill", 200))
    assert max(g.shape) > 120  # ensure the resample path actually runs
    r = dem.resample_to_max(g, 120)
    assert np.isfinite(r.values).all()
    lo, hi = float(r.values.min()), float(r.values.max())
    assert dem.ELEVATION_MIN_M < lo and hi < dem.ELEVATION_MAX_M


def test_normalize_z_rejects_unfilled_nodata():
    """The regression that produced a 1e28 mm mesh and zero pieces."""
    import pytest

    with pytest.raises(ValueError, match="non-finite"):
        dem.normalize_z(
            np.array([[1.0, np.nan]]), horizontal_scale=0.01, z_exaggeration=1.0, base_mm=3.0
        )
    with pytest.raises(ValueError, match="plausible"):
        dem.normalize_z(
            np.array([[1.0, -1e30]]), horizontal_scale=0.01, z_exaggeration=1.0, base_mm=3.0
        )


def test_gaussian_smoothing_reduces_variance():
    g = dem.fixture("hill", 64)
    smoothed = dem.gaussian_smooth(g, 2.0)
    assert smoothed.values.std() <= g.values.std()
    # no-op path
    assert dem.gaussian_smooth(g, 0.0) is g


def test_flatten_water_clamps_below_threshold():
    g = dem.fixture("coastal", 64)
    flat = dem.flatten_water(g, 0.0)
    assert flat.values.min() >= 0.0


def test_normalize_places_min_at_base_and_scales():
    vals = np.array([[100.0, 200.0], [300.0, 1100.0]])  # relief 1000 m
    z = dem.normalize_z(vals, horizontal_scale=0.01, z_exaggeration=2.0, base_mm=3.0)
    assert np.isclose(z.min(), 3.0)  # min sits at base top
    # top relief 1000 m * 0.01 mm/m * 2x = 20 mm above the base
    assert np.isclose(z.max(), 3.0 + 20.0)


def test_utm_zone_selection():
    # Montana ~ -111 lon, north -> zone 12 N -> EPSG 32612
    assert dem.utm_epsg_for_lonlat(-111.8, 48.6) == 32612
    # Southern hemisphere flips to 327xx
    assert dem.utm_epsg_for_lonlat(151.2, -33.8) == 32756


def test_reproject_to_utm_makes_metres():
    g = dem.fixture("hill", 48)
    u = dem.reproject_to_utm(g)
    assert u.crs.startswith("EPSG:326")
    w_m, h_m = dem.ground_extent_m(g)
    # ~0.2 deg lon at 48N is ~14-15 km; sanity range
    assert 5_000 < w_m < 40_000 and 15_000 < h_m < 30_000
