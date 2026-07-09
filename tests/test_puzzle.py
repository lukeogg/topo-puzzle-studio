"""Puzzle splitting: piece count, watertightness, connector pairing, proximity."""

from __future__ import annotations

import itertools

import pytest
from shapely.ops import unary_union

from topopuzzle_mesh.config import AssemblyMode, ConnectorStyle, GenerateSettings
from topopuzzle_mesh.puzzle import build_tessellation, piece_label, split_puzzle
from topopuzzle_mesh.terrain import build_terrain


@pytest.mark.parametrize("rows,cols", [(2, 2), (2, 3), (3, 3), (4, 4)])
def test_piece_count_matches_layout(hill_grid, rows, cols):
    s = GenerateSettings(size_mm=180, rows=rows, cols=cols, max_grid=120)
    res = split_puzzle(hill_grid, s)
    assert len(res.pieces) == rows * cols
    labels = {p.label for p in res.pieces}
    assert labels == {piece_label(r, c) for r in range(rows) for c in range(cols)}


def test_all_pieces_generated_when_grid_is_downsampled():
    """Regression: a DEM larger than ``max_grid`` is reprojected *and* resampled.
    Smearing the warp's nodata corners once made the terrain ~1e28 mm tall, so
    every piece's CSG intersection came back empty and the export was blocked."""
    from topopuzzle_mesh import dem

    # A mild downsample is the dangerous one: the bilinear kernel reaches past
    # the nearest-resampled mask, so the smeared cells survive the gap fill.
    grid = dem.fixture("hill", 200)
    s = GenerateSettings(size_mm=180, rows=3, cols=3, max_grid=120)
    res = split_puzzle(grid, s)
    assert len(res.pieces) == 9
    assert res.warnings == []
    assert res.terrain.z_mm.max() < 200.0  # sane millimetres, not 1e28
    assert res.terrain.max_slope_deg < 89.0


def test_all_pieces_watertight_both_modes(hill_grid):
    for mode in (AssemblyMode.SEPARATE, AssemblyMode.PRINT_IN_PLACE):
        s = GenerateSettings(size_mm=180, rows=3, cols=3, max_grid=120, assembly=mode)
        res = split_puzzle(hill_grid, s)
        assert res.warnings == []
        assert all(p.mesh.is_watertight for p in res.pieces)
        assert all(p.mesh.volume > 0 for p in res.pieces)


def test_tessellation_tiles_footprint_exactly(hill_grid):
    """Exact (pre-offset) cells cover the whole footprint with no overlap."""
    s = GenerateSettings(size_mm=180, rows=3, cols=3, max_grid=120)
    terrain = build_terrain(hill_grid, s)
    tess = build_tessellation(terrain, s)
    total = terrain.width_mm * terrain.height_mm
    union = unary_union(list(tess.values()))
    assert union.area == pytest.approx(total, rel=1e-3)
    # cells must not overlap: sum of areas ~ union area
    summed = sum(p.area for p in tess.values())
    assert summed == pytest.approx(union.area, rel=1e-3)


def test_connector_pairing_tab_has_one_socket(hill_grid):
    """A tab added to one cell is exactly the socket removed from its neighbour,
    so adjacent exact cells share their full seam boundary (no gap/overlap)."""
    s = GenerateSettings(size_mm=180, rows=3, cols=3, max_grid=120)
    terrain = build_terrain(hill_grid, s)
    tess = build_tessellation(terrain, s)
    for a, b in itertools.combinations(tess.values(), 2):
        assert not a.overlaps(b) or a.intersection(b).area < 1e-6


def test_print_in_place_has_gap(hill_grid):
    s = GenerateSettings(
        size_mm=180, rows=3, cols=3, max_grid=120,
        assembly=AssemblyMode.PRINT_IN_PLACE, gap_mm=0.4,
    )
    res = split_puzzle(hill_grid, s)
    polys = [p.fit_footprint for p in res.pieces]
    for a, b in itertools.combinations(polys, 2):
        assert not a.intersects(b) or a.distance(b) >= 0  # never overlap
    # neighbours are separated by ~ gap
    mind = min(a.distance(b) for a, b in itertools.combinations(polys, 2))
    assert mind >= s.gap_mm * 0.85


def test_separate_pieces_have_clearance(hill_grid):
    s = GenerateSettings(size_mm=180, rows=2, cols=2, max_grid=120, assembly=AssemblyMode.SEPARATE)
    s.connector.clearance_mm = 0.2
    res = split_puzzle(hill_grid, s)
    polys = [p.fit_footprint for p in res.pieces]
    mind = min(a.distance(b) for a, b in itertools.combinations(polys, 2))
    # clearance/2 per piece -> ~clearance between neighbours
    assert mind >= 0.2 * 0.85


def test_print_in_place_forces_straight_connectors():
    s = GenerateSettings(rows=3, cols=3, assembly=AssemblyMode.PRINT_IN_PLACE)
    assert s.connector.style is ConnectorStyle.STRAIGHT_TAB


def test_solid_model_single_piece(hill_grid):
    s = GenerateSettings(size_mm=150, rows=1, cols=1, max_grid=120)
    res = split_puzzle(hill_grid, s)
    assert len(res.pieces) == 1
    assert res.pieces[0].mesh.is_watertight
