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


def test_terrain_tiles_decodes_terrarium(monkeypatch):
    """Offline test of the terrarium RGB decode + stitching, with a fake session."""
    import io

    import numpy as np
    from PIL import Image

    from topopuzzle_mesh.config import Bounds
    from topopuzzle_mesh.providers.terrain_tiles import TerrainTilesProvider

    # Encode a constant 1000 m: v = 33768 -> R=131, G=232, B=0.
    tile = np.zeros((256, 256, 3), dtype=np.uint8)
    tile[..., 0], tile[..., 1], tile[..., 2] = 131, 232, 0
    buf = io.BytesIO()
    Image.fromarray(tile, "RGB").save(buf, format="PNG")
    png = buf.getvalue()

    class FakeResp:
        content = png

        def raise_for_status(self):
            pass

    class FakeSession:
        def get(self, url, timeout=0):
            return FakeResp()

    prov = TerrainTilesProvider(session=FakeSession())
    grid = prov.get_elevation_grid(Bounds(west=-111.9, south=48.5, east=-111.7, north=48.7), 90.0)
    lo, hi = grid.valid_min_max()
    assert abs(lo - 1000.0) < 1.0 and abs(hi - 1000.0) < 1.0
    assert "SRTM" in grid.attribution.sources
    assert grid.attribution.provider.startswith("AWS")


def test_geotiff_crops_to_bounds(geotiff_path):
    from topopuzzle_mesh.config import Bounds

    full = LocalGeoTIFFProvider(geotiff_path).get_elevation_grid(None)
    # A sub-rectangle of the Montana fixture extent (-111.90..-111.70, 48.50..48.70).
    sub = LocalGeoTIFFProvider(geotiff_path).get_elevation_grid(
        Bounds(west=-111.85, south=48.55, east=-111.75, north=48.65)
    )
    assert sub.cols < full.cols and sub.rows < full.rows
    # A bbox with no overlap falls back to the full raster extent (no garbage).
    far = LocalGeoTIFFProvider(geotiff_path).get_elevation_grid(
        Bounds(west=10.0, south=10.0, east=10.1, north=10.1)
    )
    assert far.shape == full.shape


def test_cli_blocks_export_on_hard_errors(geotiff_path, tmp_path):
    # 900 mm on a 250 mm plate -> build-volume error -> export blocked, no ZIP.
    out = tmp_path / "blocked.zip"
    res = runner.invoke(app, ["generate", "--geotiff", geotiff_path, "--rows", "2",
                              "--cols", "2", "--size-mm", "900", "--output", str(out)])
    assert res.exit_code == 1
    assert not out.exists()
    assert "blocked" in res.output.lower()
    # --force writes it anyway.
    res2 = runner.invoke(app, ["generate", "--geotiff", geotiff_path, "--rows", "2",
                               "--cols", "2", "--size-mm", "900", "--output", str(out), "--force"])
    assert res2.exit_code == 0 and out.exists()


def test_cli_tray_flag_adds_tray(geotiff_path, tmp_path):
    import zipfile as zf

    out = tmp_path / "tray.zip"
    res = runner.invoke(app, ["generate", "--geotiff", geotiff_path, "--rows", "2",
                              "--cols", "2", "--size-mm", "150", "--tray", "--output", str(out)])
    assert res.exit_code == 0
    assert "tray.stl" in zf.ZipFile(out).namelist()


def test_cli_calibrate_emits_coupon(tmp_path):
    out = tmp_path / "coupon.stl"
    result = runner.invoke(app, ["calibrate", "--clearance-mm", "0.15", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0
