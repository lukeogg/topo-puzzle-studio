"""Optional display tray/frame that the assembled puzzle drops into."""

from __future__ import annotations

import trimesh

from .config import GenerateSettings
from .terrain import TerrainResult


def build_tray(terrain: TerrainResult, settings: GenerateSettings, floor_mm: float = 2.0) -> trimesh.Trimesh:
    """A rectangular tray with a raised border and a recess matching the puzzle
    footprint (plus fit gap).  Origin at the tray's min corner, sitting on z=0."""
    t = settings.tray
    W, H = terrain.width_mm, terrain.height_mm
    rw, rh = W + 2 * t.fit_gap_mm, H + 2 * t.fit_gap_mm  # recess opening
    ow, oh = rw + 2 * t.wall_mm, rh + 2 * t.wall_mm  # outer footprint
    oz = floor_mm + t.border_h_mm

    outer = trimesh.creation.box(extents=(ow, oh, oz))
    outer.apply_translation((ow / 2, oh / 2, oz / 2))

    recess = trimesh.creation.box(extents=(rw, rh, t.border_h_mm + 1.0))
    recess.apply_translation((ow / 2, oh / 2, floor_mm + (t.border_h_mm + 1.0) / 2))

    tray = trimesh.boolean.difference([outer, recess], engine="manifold")
    tray.fix_normals()
    return tray
