"""Terrain solid: watertightness, dimensions, base thickness."""

from __future__ import annotations

import numpy as np

from topopuzzle_mesh.terrain import build_terrain, heightfield_solid


def test_heightfield_solid_is_watertight():
    z = np.array([[3.0, 4.0, 5.0], [3.5, 6.0, 4.5], [3.0, 3.2, 3.1]])
    x = np.array([0.0, 10.0, 20.0])
    y = np.array([20.0, 10.0, 0.0])
    m = heightfield_solid(z, x, y)
    assert m.is_watertight
    assert m.is_winding_consistent
    assert m.volume > 0


def test_terrain_watertight_for_all_fixtures(any_grid, base_settings):
    r = build_terrain(any_grid, base_settings)
    assert r.mesh.is_watertight
    assert r.mesh.is_winding_consistent
    assert r.mesh.volume > 0


def test_longest_edge_matches_size_mm(hill_grid, base_settings):
    r = build_terrain(hill_grid, base_settings)
    longest = max(r.width_mm, r.height_mm)
    assert abs(longest - base_settings.size_mm) < 0.5
    # model extents agree with reported footprint
    assert abs(r.mesh.extents[0] - r.width_mm) < 0.5
    assert abs(r.mesh.extents[1] - r.height_mm) < 0.5


def test_base_thickness_present(hill_grid, base_settings):
    r = build_terrain(hill_grid, base_settings)
    assert r.mesh.bounds[0][2] <= 1e-6  # bottom at z=0
    assert r.z_mm.min() >= base_settings.base_mm - 1e-6


def test_exaggeration_increases_height(hill_grid):
    from topopuzzle_mesh.config import GenerateSettings

    low = build_terrain(hill_grid, GenerateSettings(size_mm=150, z_exaggeration=1.0, max_grid=120))
    high = build_terrain(hill_grid, GenerateSettings(size_mm=150, z_exaggeration=3.0, max_grid=120))
    assert high.mesh.extents[2] > low.mesh.extents[2]
