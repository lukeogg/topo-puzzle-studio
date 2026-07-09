"""Provider loading (offline GeoTIFF) and CLI smoke tests. No network."""

from __future__ import annotations

import zipfile

from typer.testing import CliRunner

from topopuzzle_mesh.cli import app
from topopuzzle_mesh.providers import LocalGeoTIFFProvider, get_provider

runner = CliRunner()


def test_geotiff_provider_loads_full_extent(geotiff_path):
    grid = LocalGeoTIFFProvider(geotiff_path).get_elevation_grid(None)
    assert grid.shape[0] > 10 and grid.shape[1] > 10
    assert grid.attribution.provider == "Local GeoTIFF"
    lo, hi = grid.valid_min_max()
    assert hi > lo


def test_get_provider_factory(geotiff_path):
    p = get_provider("geotiff", geotiff_path=geotiff_path)
    assert isinstance(p, LocalGeoTIFFProvider)


def test_cli_generate_produces_zip(geotiff_path, tmp_path):
    out = tmp_path / "puzzle.zip"
    result = runner.invoke(
        app,
        ["generate", "--geotiff", geotiff_path, "--rows", "2", "--cols", "2",
         "--size-mm", "150", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    z = zipfile.ZipFile(out)
    assert len([n for n in z.namelist() if n.endswith(".stl")]) >= 4


def test_cli_calibrate_emits_coupon(tmp_path):
    out = tmp_path / "coupon.stl"
    result = runner.invoke(app, ["calibrate", "--clearance-mm", "0.15", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0
