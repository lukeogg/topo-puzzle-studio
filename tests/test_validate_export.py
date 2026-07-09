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


def test_3mf_named_objects_and_units(hill_grid, base_settings):
    out = generate(base_settings.model_copy(update={"rows": 2, "cols": 2, "formats": ["3mf"]}), grid=hill_grid)
    buf = "/tmp/_test_pkg3.zip"
    package_zip(out.result, out.report, buf)
    z = zipfile.ZipFile(buf)
    scene = trimesh.load(io.BytesIO(z.read("model.3mf")), file_type="3mf")
    assert len(scene.geometry) == 4
    assert scene.units == "millimeter"
