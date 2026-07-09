"""Shared fixtures — synthetic DEMs and a GeoTIFF writer.  No network required."""

from __future__ import annotations

import numpy as np
import pytest

from topopuzzle_mesh import dem
from topopuzzle_mesh.config import GenerateSettings


@pytest.fixture(params=["ramp", "hill", "flat", "coastal", "nodata"])
def any_grid(request):
    return dem.fixture(request.param, 48)


@pytest.fixture
def hill_grid():
    return dem.fixture("hill", 64)


@pytest.fixture
def base_settings():
    return GenerateSettings(size_mm=150.0, base_mm=3.0, z_exaggeration=1.8, max_grid=120)


@pytest.fixture
def geotiff_path(tmp_path):
    """Write a synthetic hill DEM to a GeoTIFF and return its path."""
    import rasterio
    from rasterio.transform import from_bounds

    g = dem.fixture("hill", 100)
    b = g.bounds
    path = tmp_path / "fixture.tif"
    tr = from_bounds(b[0], b[1], b[2], b[3], g.cols, g.rows)
    with rasterio.open(
        path, "w", driver="GTiff", height=g.rows, width=g.cols, count=1,
        dtype="float32", crs="EPSG:4326", transform=tr, nodata=-9999,
    ) as ds:
        ds.write(g.values.astype(np.float32), 1)
    return str(path)
