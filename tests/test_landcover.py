"""Tier-4 land-cover colouring: providers, resample, purge, shells. No network."""

from __future__ import annotations

import io
import zipfile

import numpy as np
import trimesh

from topopuzzle_mesh.config import GenerateSettings, LandCoverClass, LandCoverSettings
from topopuzzle_mesh.export import attribution_text, package_zip
from topopuzzle_mesh.landcover import purge_filter, resample_classes_to_mesh
from topopuzzle_mesh.pipeline import generate
from topopuzzle_mesh.providers.landcover import (
    _WC_ATTRIBUTION,
    LocalLandCoverProvider,
    _worldcover_tile,
)
from topopuzzle_mesh.puzzle import split_puzzle
from topopuzzle_mesh.terrain import build_terrain

# Same geographic extent as the synthetic hill fixture.
FIXTURE_BOUNDS = (-111.90, 48.50, -111.70, 48.70)


def _class_raster(tmp_path, n=40):
    """Classified GeoTIFF: west half tree(10), east half grass(30), a water(80) block."""
    from rasterio.transform import from_bounds

    w, s, e, nth = FIXTURE_BOUNDS
    arr = np.full((n, n), 10, dtype=np.uint8)
    arr[:, n // 2:] = 30
    arr[n - 8:, n // 2 - 4:n // 2 + 4] = 80  # a water block spanning the seam
    transform = from_bounds(w, s, e, nth, n, n)
    path = tmp_path / "landcover.tif"
    import rasterio

    with rasterio.open(
        path, "w", driver="GTiff", height=n, width=n, count=1,
        dtype="uint8", crs="EPSG:4326", transform=transform, nodata=0,
    ) as ds:
        ds.write(arr, 1)
    return str(path)


def test_worldcover_tile_name():
    assert _worldcover_tile(48.6, -111.8) == "N48W114"
    assert "CC BY" in _WC_ATTRIBUTION.license


def test_local_provider_reads_classes(tmp_path):
    lc = LocalLandCoverProvider(_class_raster(tmp_path)).get_landcover_grid()
    present = set(np.unique(lc.classes).tolist())
    assert {10, 30, 80} <= present
    assert lc.legend[10][0] == "tree cover"


def test_resample_aligns_classes_to_mesh(tmp_path, hill_grid):
    lc = LocalLandCoverProvider(_class_raster(tmp_path)).get_landcover_grid()
    terrain = build_terrain(hill_grid, GenerateSettings(size_mm=180, rows=1, cols=1, max_grid=100))
    mesh_classes = resample_classes_to_mesh(lc, terrain)
    assert mesh_classes.shape == terrain.z_mm.shape
    present = set(np.unique(mesh_classes).tolist())
    assert {10, 30} <= present  # west/east halves both land on the mesh


def test_purge_filter_drops_small_regions():
    arr = np.full((20, 20), 10, dtype=np.int32)
    arr[0, 0] = 50  # a single-cell speckle
    out = purge_filter(arr, cell_area_mm2=1.0, min_region_mm2=3.0, nodata=0)
    assert out[0, 0] == 0  # 1 mm² < 3 mm² -> dropped to nodata
    assert (out == 10).sum() > 300  # the big region survives


def test_landcover_shells_are_watertight_named_objects(tmp_path, hill_grid):
    lc = LocalLandCoverProvider(_class_raster(tmp_path)).get_landcover_grid()
    s = GenerateSettings(size_mm=180, rows=1, cols=1, max_grid=100,
                         landcover=LandCoverSettings(enabled=True, shell_mm=0.8))
    res = split_puzzle(hill_grid, s, landcover=lc)
    assert len(res.landcover_objects) >= 2
    names = " ".join(n for n, _, _ in res.landcover_objects)
    assert "tree" in names and "grassland" in names
    for name, mesh, hexc in res.landcover_objects:
        assert mesh.is_watertight and mesh.volume > 0, name
    assert any("land cover" in w for w in res.warnings)


def test_explicit_mapping_selects_only_mapped_classes(tmp_path, hill_grid):
    lc = LocalLandCoverProvider(_class_raster(tmp_path)).get_landcover_grid()
    ls = LandCoverSettings(
        enabled=True,
        mapping=[LandCoverClass(code=10, name="forest", hex="#123456")],
    )
    s = GenerateSettings(size_mm=180, rows=1, cols=1, max_grid=100, landcover=ls)
    res = split_puzzle(hill_grid, s, landcover=lc)
    names = [n for n, _, _ in res.landcover_objects]
    assert any("forest" in n for n in names)  # class 10 is mapped
    assert not any("grass" in n for n in names)  # class 30 is not
    assert any(n.endswith("-base") for n in names)  # base body keeps it complete


def test_landcover_partitions_each_piece(tmp_path, hill_grid):
    lc = LocalLandCoverProvider(_class_raster(tmp_path)).get_landcover_grid()
    s = GenerateSettings(size_mm=180, rows=2, cols=2, max_grid=100,
                         landcover=LandCoverSettings(enabled=True))
    res = split_puzzle(hill_grid, s, landcover=lc)
    by_label: dict[str, list] = {}
    for name, mesh, _ in res.landcover_objects:
        by_label.setdefault(name.split("-")[0], []).append((name, mesh))
    assert len(by_label) == 4  # one group per piece
    for p in res.pieces:
        objs = by_label[p.label]
        assert any(n.endswith("-base") for n, _ in objs)  # complete base body
        total = sum(m.volume for _, m in objs)
        assert abs(total - p.mesh.volume) / p.mesh.volume < 0.03  # partitions the piece


def test_cli_landcover_flag(tmp_path, geotiff_path):
    from typer.testing import CliRunner

    from topopuzzle_mesh.cli import app

    raster = _class_raster(tmp_path)
    out = tmp_path / "lc.zip"
    res = CliRunner().invoke(app, [
        "generate", "--geotiff", geotiff_path, "--rows", "1", "--cols", "1",
        "--size-mm", "150", "--landcover", "--landcover-raster", raster,
        "--landcover-map", "10:forest:#2e7d32,30:grass:#c8a165", "--output", str(out),
    ])
    assert res.exit_code == 0, res.output
    assert "model-landcover.3mf" in zipfile.ZipFile(out).namelist()


def test_landcover_per_piece_and_export(tmp_path, hill_grid):
    lc = LocalLandCoverProvider(_class_raster(tmp_path)).get_landcover_grid()
    s = GenerateSettings(size_mm=180, rows=2, cols=2, max_grid=100,
                         landcover=LandCoverSettings(enabled=True))
    out = generate(s, grid=hill_grid, landcover=lc)
    assert all(p.mesh.is_watertight for p in out.result.pieces)  # split unaffected
    manifest = attribution_text(out.result)
    assert "Local classified raster" in manifest
    package_zip(out.result, out.report, "/tmp/_test_landcover.zip")
    z = zipfile.ZipFile("/tmp/_test_landcover.zip")
    assert "model-landcover.3mf" in z.namelist()
    scene = trimesh.load(io.BytesIO(z.read("model-landcover.3mf")), file_type="3mf")
    assert len(scene.geometry) >= 2
