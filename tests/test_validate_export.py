"""Validation guardrails, export integrity, and ZIP manifest completeness."""

from __future__ import annotations

import io
import json
import zipfile

import trimesh

from topopuzzle_mesh.config import AssemblyMode, GenerateSettings
from topopuzzle_mesh.export import calibration_coupon, package_zip
from topopuzzle_mesh.pipeline import generate
from topopuzzle_mesh.puzzle import split_puzzle
from topopuzzle_mesh.validate import validate


def test_build_volume_error_triggers(hill_grid):
    # 900 mm model on a 250 mm plate -> pieces exceed the plate.
    s = GenerateSettings(size_mm=900, rows=2, cols=2, max_grid=100)
    res = split_puzzle(hill_grid, s)
    rep = validate(res)
    names = {c.name: c for c in rep.checks}
    assert not names["piece_build_volume"].ok
    assert rep.has_errors


def test_print_in_place_assembled_volume_check(hill_grid):
    s = GenerateSettings(size_mm=300, rows=3, cols=3, max_grid=100, assembly=AssemblyMode.PRINT_IN_PLACE)
    res = split_puzzle(hill_grid, s)
    rep = validate(res)
    names = {c.name: c for c in rep.checks}
    assert not names["assembled_build_volume"].ok


def test_valid_model_passes_all_checks(hill_grid, base_settings):
    res = split_puzzle(hill_grid, base_settings)
    rep = validate(res)
    assert not rep.has_errors


def test_pip_proximity_check_present(hill_grid):
    s = GenerateSettings(size_mm=180, rows=3, cols=3, max_grid=100, assembly=AssemblyMode.PRINT_IN_PLACE)
    res = split_puzzle(hill_grid, s)
    rep = validate(res)
    names = {c.name for c in rep.checks}
    assert "pip_proximity" in names


def test_coupon_is_watertight():
    s = GenerateSettings(assembly=AssemblyMode.SEPARATE)
    s.connector.clearance_mm = 0.2
    coupon = calibration_coupon(s)
    assert coupon.is_watertight
    assert coupon.volume > 0


def test_zip_manifest_contains_attribution_and_settings(hill_grid, base_settings):
    out = generate(base_settings.model_copy(update={"rows": 2, "cols": 2}), grid=hill_grid)
    buf = "/tmp/_test_pkg.zip"
    package_zip(out.result, out.report, buf)
    z = zipfile.ZipFile(buf)
    names = set(z.namelist())
    for required in ("attribution.txt", "settings.json", "validation-report.json",
                     "color-changes.txt", "print-notes.md", "README.md", "coupon.stl"):
        assert required in names, required
    # settings JSON round-trips and carries footprint
    settings = json.loads(z.read("settings.json"))
    assert settings["_piece_count"] == 4
    assert "attribution" not in settings  # attribution lives in its own file
    attribution = z.read("attribution.txt").decode()
    assert "Elevation provider" in attribution and "License" in attribution


def test_every_exported_stl_reloads_watertight(hill_grid, base_settings):
    out = generate(base_settings.model_copy(update={"rows": 3, "cols": 3}), grid=hill_grid)
    buf = "/tmp/_test_pkg2.zip"
    package_zip(out.result, out.report, buf)
    z = zipfile.ZipFile(buf)
    piece_stls = [n for n in z.namelist() if n.endswith(".stl") and n not in ("coupon.stl", "combined.stl")]
    assert len(piece_stls) == 9
    for n in piece_stls:
        m = trimesh.load(io.BytesIO(z.read(n)), file_type="stl")
        assert m.is_watertight, n


def test_combined_stl_only_with_its_token(hill_grid, base_settings):
    # Without the combined-stl token there is no combined.stl…
    out = generate(base_settings.model_copy(update={"rows": 2, "cols": 2, "formats": ["stl", "3mf"]}), grid=hill_grid)
    package_zip(out.result, out.report, "/tmp/_test_nocomb.zip")
    assert "combined.stl" not in zipfile.ZipFile("/tmp/_test_nocomb.zip").namelist()
    # …and with it, there is.
    out2 = generate(base_settings.model_copy(update={"rows": 2, "cols": 2, "formats": ["stl", "combined-stl"]}), grid=hill_grid)
    package_zip(out2.result, out2.report, "/tmp/_test_comb.zip")
    assert "combined.stl" in zipfile.ZipFile("/tmp/_test_comb.zip").namelist()


def test_tray_packaged_and_watertight(hill_grid, base_settings):
    s = base_settings.model_copy(update={"rows": 2, "cols": 2})
    s.tray.enabled = True
    out = generate(s, grid=hill_grid)
    names = {c.name for c in out.report.checks}
    assert "tray_build_volume" in names
    package_zip(out.result, out.report, "/tmp/_test_tray.zip")
    z = zipfile.ZipFile("/tmp/_test_tray.zip")
    assert "tray.stl" in z.namelist()
    tray = trimesh.load(io.BytesIO(z.read("tray.stl")), file_type="stl")
    assert tray.is_watertight and tray.volume > 0


def _oversized_tray_settings(base_settings):
    # Narrow plate in X so only the X axis exceeds -> a clean single-axis split.
    from topopuzzle_mesh.config import BuildVolume

    s = base_settings.model_copy(
        update={"rows": 2, "cols": 2, "size_mm": 300,
                "build_volume": BuildVolume(x_mm=200, y_mm=400, z_mm=250)}
    )
    s.tray.enabled = True
    return s


def test_tray_splits_into_pinned_halves_when_oversized(hill_grid, base_settings):
    from topopuzzle_mesh.tray import split_tray

    s = _oversized_tray_settings(base_settings)
    out = generate(s, grid=hill_grid)
    parts, warns = split_tray(out.result.terrain, s)
    assert [n for n, _ in parts] == ["tray-half-A", "tray-half-B"]
    assert warns == []  # single-axis split resolves the fit cleanly
    for name, m in parts:
        assert m.is_watertight and m.volume > 0, name
        assert m.extents[0] <= s.build_volume.x_mm and m.extents[1] <= s.build_volume.y_mm


def test_tray_split_reported_and_zipped(hill_grid, base_settings):
    s = _oversized_tray_settings(base_settings)
    out = generate(s, grid=hill_grid)
    check = next(c for c in out.report.checks if c.name == "tray_build_volume")
    assert check.ok and "pinned halves" in check.message
    package_zip(out.result, out.report, "/tmp/_test_traysplit.zip")
    names = set(zipfile.ZipFile("/tmp/_test_traysplit.zip").namelist())
    assert "tray-half-A.stl" in names and "tray-half-B.stl" in names
    assert "tray.stl" not in names
    z = zipfile.ZipFile("/tmp/_test_traysplit.zip")
    for n in ("tray-half-A.stl", "tray-half-B.stl"):
        m = trimesh.load(io.BytesIO(z.read(n)), file_type="stl")
        assert m.is_watertight and m.volume > 0


def test_small_tray_stays_single(hill_grid, base_settings):
    from topopuzzle_mesh.tray import split_tray

    s = base_settings.model_copy(update={"rows": 2, "cols": 2})
    s.tray.enabled = True
    out = generate(s, grid=hill_grid)
    parts, warns = split_tray(out.result.terrain, s)
    assert [n for n, _ in parts] == ["tray"] and warns == []


def test_pip_proximity_uses_mesh_and_footprint(hill_grid):
    """The PIP gap check runs both the footprint bound and the mesh-level check."""
    s = GenerateSettings(size_mm=180, rows=2, cols=2, max_grid=100, assembly=AssemblyMode.PRINT_IN_PLACE, gap_mm=0.4)
    res = split_puzzle(hill_grid, s)
    rep = validate(res)
    prox = next(c for c in rep.checks if c.name == "pip_proximity")
    assert prox.ok  # 0.4 mm gap is respected in the actual meshes


def _banded_settings(hill_grid, base_settings):
    """Settings with three elevation bands spanning the processed terrain range."""
    from topopuzzle_mesh.config import ElevationBand
    from topopuzzle_mesh.terrain import build_terrain

    s = base_settings.model_copy(update={"rows": 1, "cols": 1, "max_grid": 100})
    terrain = build_terrain(hill_grid, s)
    lo = float(terrain.grid.values.min())
    hi = float(terrain.grid.values.max())
    bands = [
        ElevationBand(min_m=lo, name="low", hex="#2e7d32"),
        ElevationBand(min_m=lo + (hi - lo) * 0.33, name="mid", hex="#c8a165"),
        ElevationBand(min_m=lo + (hi - lo) * 0.66, name="high", hex="#ffffff"),
    ]
    return terrain, s.model_copy(update={"contour_bands": True, "bands": bands})


def test_contour_bands_partition_solid(hill_grid, base_settings):
    from topopuzzle_mesh.contour import contour_band_meshes

    terrain, s = _banded_settings(hill_grid, base_settings)
    slabs = contour_band_meshes(terrain, s)
    assert len(slabs) == 3
    names = [name for name, _, _ in slabs]
    assert names == ["low", "mid", "high"]
    for _, m, _ in slabs:
        assert m.is_watertight and m.volume > 0
    # The slabs partition the solid: their volumes sum to the whole (CSG-exact).
    total = sum(m.volume for _, m, _ in slabs)
    assert abs(total - terrain.mesh.volume) / terrain.mesh.volume < 0.01


def test_contour_bands_in_zip_as_named_objects(hill_grid, base_settings):
    _, s = _banded_settings(hill_grid, base_settings)
    out = generate(s, grid=hill_grid)
    buf = "/tmp/_test_banded.zip"
    package_zip(out.result, out.report, buf)
    z = zipfile.ZipFile(buf)
    assert "model-banded.3mf" in z.namelist()
    scene = trimesh.load(io.BytesIO(z.read("model-banded.3mf")), file_type="3mf")
    assert len(scene.geometry) == 3
    assert scene.units == "millimeter"


def test_no_banded_3mf_without_flag(hill_grid, base_settings):
    _, s = _banded_settings(hill_grid, base_settings)
    out = generate(s.model_copy(update={"contour_bands": False}), grid=hill_grid)
    package_zip(out.result, out.report, "/tmp/_test_nobanded.zip")
    assert "model-banded.3mf" not in zipfile.ZipFile("/tmp/_test_nobanded.zip").namelist()


def test_magnet_pocket_recesses_and_stays_watertight(hill_grid, base_settings):
    from topopuzzle_mesh.config import MagnetSettings
    from topopuzzle_mesh.magnets import add_magnet_pockets

    res = split_puzzle(hill_grid, base_settings.model_copy(update={"rows": 2, "cols": 2, "max_grid": 100}))
    p = res.pieces[0]
    mag = MagnetSettings(enabled=True, diameter_mm=6.0, depth_mm=2.0)
    out, warn = add_magnet_pockets(p.mesh, p.fit_footprint, mag, base_settings.base_mm)
    assert warn is None
    assert out.is_watertight and out.volume > 0
    removed = p.mesh.volume - out.volume
    ideal = 3.14159 * (3.0**2) * 2.0  # pi r^2 depth
    assert removed > ideal * 0.5  # a real pocket of roughly the right size was cut


def test_magnet_pocket_skipped_when_piece_too_small():
    import trimesh as tm
    from shapely.geometry import box as sbox

    from topopuzzle_mesh.config import MagnetSettings

    from topopuzzle_mesh.magnets import add_magnet_pockets

    mesh = tm.creation.box(extents=(5, 5, 3))
    mag = MagnetSettings(enabled=True, diameter_mm=6.0, margin_mm=2.0)
    out, warn = add_magnet_pockets(mesh, sbox(0, 0, 5, 5), mag, 3.0)
    assert warn is not None and "too small" in warn
    assert out is mesh  # unchanged


def test_magnet_pockets_applied_in_export(hill_grid, base_settings):
    s = base_settings.model_copy(update={"rows": 2, "cols": 2})
    s.magnets.enabled = True
    out = generate(s, grid=hill_grid)
    package_zip(out.result, out.report, "/tmp/_test_magnets.zip")
    z = zipfile.ZipFile("/tmp/_test_magnets.zip")
    piece_stls = [n for n in z.namelist() if n.endswith(".stl") and n not in ("coupon.stl", "combined.stl")]
    assert len(piece_stls) == 4
    for n in piece_stls:
        m = trimesh.load(io.BytesIO(z.read(n)), file_type="stl")
        assert m.is_watertight, n


def test_3mf_named_objects_and_units(hill_grid, base_settings):
    out = generate(base_settings.model_copy(update={"rows": 2, "cols": 2, "formats": ["3mf"]}), grid=hill_grid)
    buf = "/tmp/_test_pkg3.zip"
    package_zip(out.result, out.report, buf)
    z = zipfile.ZipFile(buf)
    scene = trimesh.load(io.BytesIO(z.read("model.3mf")), file_type="3mf")
    assert len(scene.geometry) == 4
    assert scene.units == "millimeter"
