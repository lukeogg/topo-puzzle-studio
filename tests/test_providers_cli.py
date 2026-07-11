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


def test_opentopodata_samples_grid(monkeypatch):
    """Offline test of the point-lookup sampling, batching, and nodata handling."""
    from topopuzzle_mesh.config import Bounds
    from topopuzzle_mesh.providers.opentopodata import OpenTopoDataProvider

    calls = {"n": 0, "locations": 0}

    class FakeResp:
        def __init__(self, n_locations):
            self._n = n_locations

        def raise_for_status(self):
            pass

        def json(self):
            # One result per requested location; a null over the "ocean" first cell.
            results = [{"elevation": 1234.0} for _ in range(self._n)]
            if calls["n"] == 1:
                results[0]["elevation"] = None
            return {"status": "OK", "results": results}

    class FakeSession:
        def get(self, url, params=None, timeout=0):
            calls["n"] += 1
            n = len(params["locations"].split("|"))
            calls["locations"] += n
            return FakeResp(n)

    # Cap forces a small grid; batch_size forces >1 request so batching is exercised.
    prov = OpenTopoDataProvider(
        dataset="srtm30m", session=FakeSession(), max_points=40, batch_size=16
    )
    grid = prov.get_elevation_grid(
        Bounds(west=-111.9, south=48.5, east=-111.7, north=48.7), 30.0
    )
    assert grid.shape[0] * grid.shape[1] <= 40
    assert calls["locations"] == grid.shape[0] * grid.shape[1]
    assert calls["n"] >= 2  # batched across multiple requests
    lo, hi = grid.valid_min_max()
    assert abs(lo - 1234.0) < 1.0 and abs(hi - 1234.0) < 1.0
    assert grid.nodata_mask.any()  # the null cell became nodata
    assert grid.attribution.provider.startswith("OpenTopoData")
    assert "srtm30m" in grid.attribution.sources


def test_opentopodata_via_factory():
    from topopuzzle_mesh.providers import OpenTopoDataProvider, get_provider

    assert isinstance(get_provider("opentopodata"), OpenTopoDataProvider)


def _fake_geotiff_bytes(bounds, value=815.0, n=16):
    """A single-band float32 GeoTIFF covering ``bounds`` (EPSG:4326)."""
    import numpy as np
    from rasterio.io import MemoryFile
    from rasterio.transform import from_bounds

    data = np.full((n, n), value, dtype=np.float32)
    transform = from_bounds(bounds.west, bounds.south, bounds.east, bounds.north, n, n)
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff", height=n, width=n, count=1, dtype="float32",
            crs="EPSG:4326", transform=transform,
        ) as ds:
            ds.write(data, 1)
        return mem.read()


class _FakeGeoTIFFSession:
    """A session whose GET returns fixed GeoTIFF bytes; records last params."""

    def __init__(self, tiff_bytes):
        self._tiff = tiff_bytes
        self.last_params = None

    def get(self, url, params=None, timeout=0):
        self.last_params = params

        class _Resp:
            def __init__(self, content):
                self.content = content

            def raise_for_status(self):
                pass

        return _Resp(self._tiff)


def test_usgs_3dep_decodes_geotiff():
    from topopuzzle_mesh.config import Bounds
    from topopuzzle_mesh.providers.usgs_3dep import USGS3DEPProvider

    bounds = Bounds(west=-111.9, south=48.5, east=-111.7, north=48.7)
    sess = _FakeGeoTIFFSession(_fake_geotiff_bytes(bounds, value=1500.0))
    grid = USGS3DEPProvider(session=sess).get_elevation_grid(bounds, 30.0)
    lo, hi = grid.valid_min_max()
    assert abs(lo - 1500.0) < 1.0 and abs(hi - 1500.0) < 1.0
    assert "USGS 3DEP" in grid.attribution.sources
    # exportImage request carried a bbox and an F32 pixel type.
    assert sess.last_params["pixelType"] == "F32"
    assert sess.last_params["bboxSR"] == "4326"


def test_opentopography_requires_key():
    import pytest

    from topopuzzle_mesh.config import Bounds
    from topopuzzle_mesh.providers.opentopography import OpenTopographyProvider

    bounds = Bounds(west=-111.9, south=48.5, east=-111.7, north=48.7)
    prov = OpenTopographyProvider(api_key=None, session=_FakeGeoTIFFSession(b""))
    prov.api_key = None  # ensure no ambient env key leaks in
    with pytest.raises(ValueError, match="API key"):
        prov.get_elevation_grid(bounds, 30.0)


def test_opentopography_decodes_geotiff():
    from topopuzzle_mesh.config import Bounds
    from topopuzzle_mesh.providers.opentopography import OpenTopographyProvider

    bounds = Bounds(west=6.0, south=45.0, east=6.2, north=45.2)
    sess = _FakeGeoTIFFSession(_fake_geotiff_bytes(bounds, value=2100.0))
    prov = OpenTopographyProvider(demtype="COP30", api_key="test-key", session=sess)
    grid = prov.get_elevation_grid(bounds, 30.0)
    lo, hi = grid.valid_min_max()
    assert abs(lo - 2100.0) < 1.0 and abs(hi - 2100.0) < 1.0
    assert grid.attribution.provider.startswith("OpenTopography")
    assert sess.last_params["demtype"] == "COP30"
    assert sess.last_params["API_Key"] == "test-key"


def test_3dep_and_opentopography_via_factory():
    from topopuzzle_mesh.providers import (
        OpenTopographyProvider,
        USGS3DEPProvider,
        get_provider,
    )

    assert isinstance(get_provider("usgs-3dep"), USGS3DEPProvider)
    assert isinstance(get_provider("opentopography"), OpenTopographyProvider)


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


def test_cli_magnets_contour_and_connector_style(geotiff_path, tmp_path):
    out = tmp_path / "m.zip"
    res = runner.invoke(app, [
        "generate", "--geotiff", geotiff_path, "--rows", "2", "--cols", "2",
        "--size-mm", "150", "--magnets", "--connector", "organic-tab",
        "--contour-bands", "--band", "0:low:#2e7d32", "--output", str(out),
    ])
    assert res.exit_code == 0, res.output
    names = zipfile.ZipFile(out).namelist()
    assert "model-banded.3mf" in names


def test_cli_calibrate_emits_coupon(tmp_path):
    out = tmp_path / "coupon.stl"
    result = runner.invoke(app, ["calibrate", "--clearance-mm", "0.15", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0
