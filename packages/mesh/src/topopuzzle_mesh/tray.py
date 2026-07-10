"""Optional display tray/frame that the assembled puzzle drops into.

When the tray is larger than the build plate it can be split into two halves
joined by alignment pins, so each half prints on its own and presses together
afterwards.
"""

from __future__ import annotations

import numpy as np
import trimesh

from .config import GenerateSettings, TraySettings
from .terrain import TerrainResult

FLOOR_MM = 2.0


def tray_outer_size(terrain: TerrainResult, t: TraySettings) -> tuple[float, float, float]:
    """Outer (width, height, height-z) of the tray solid in mm."""
    W, H = terrain.width_mm, terrain.height_mm
    ow = W + 2 * (t.fit_gap_mm + t.wall_mm)
    oh = H + 2 * (t.fit_gap_mm + t.wall_mm)
    oz = FLOOR_MM + t.border_h_mm
    return ow, oh, oz


def build_tray(terrain: TerrainResult, settings: GenerateSettings, floor_mm: float = FLOOR_MM) -> trimesh.Trimesh:
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


def _pin(radius: float, length: float, along_x: bool, center) -> trimesh.Trimesh:
    """A cylinder of ``length`` centred at ``center``, axis along X or Y."""
    pin = trimesh.creation.cylinder(radius=radius, height=length, sections=32)
    # Default axis is Z; rotate onto X or Y.
    axis = (0, 1, 0) if along_x else (1, 0, 0)
    pin.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, axis))
    pin.apply_translation(center)
    return pin


def _half(tray: trimesh.Trimesh, lo, hi) -> trimesh.Trimesh:
    """Intersect the tray with an axis-aligned box spanning [lo, hi] (xyz)."""
    ext = [hi[i] - lo[i] for i in range(3)]
    cutter = trimesh.creation.box(extents=ext)
    cutter.apply_translation([(lo[i] + hi[i]) / 2.0 for i in range(3)])
    out = trimesh.boolean.intersection([tray, cutter], engine="manifold")
    out.fix_normals()
    return out


def split_tray(
    terrain: TerrainResult, settings: GenerateSettings
) -> tuple[list[tuple[str, trimesh.Trimesh]], list[str]]:
    """Return tray part(s) ready for export, plus any warnings.

    Fits on the plate → one ``("tray", mesh)``.  Oversized and splitting enabled →
    two halves joined by alignment pins, cut across the longer over-plate axis.
    """
    t = settings.tray
    bv = settings.build_volume
    tray = build_tray(terrain, settings)
    ow, oh, oz = tray_outer_size(terrain, t)

    fits = ow <= bv.x_mm and oh <= bv.y_mm
    if fits or not t.split_oversize:
        return [("tray", tray)], []

    over_x, over_y = ow > bv.x_mm, oh > bv.y_mm
    warnings: list[str] = []
    if over_x and over_y:
        warnings.append(
            "tray exceeds the plate on both axes; even split into halves it may not "
            "fit — consider a smaller model or omitting the tray"
        )
    split_x = ow >= oh if (over_x and over_y) else over_x

    r = min(t.pin_diameter_mm / 2.0, (t.wall_mm - 1.0) / 2.0)
    r = max(r, 0.5)
    hole_r = r + t.pin_clearance_mm
    L = t.pin_length_mm
    z = oz / 2.0

    if split_x:
        cut = ow / 2.0
        # Pin seats sit in the two perimeter walls (full-height solid) at the cut.
        seats = [(cut, t.wall_mm / 2.0, z), (cut, oh - t.wall_mm / 2.0, z)]
        a_lo, a_hi = (0.0, 0.0, 0.0), (cut, oh, oz)
        b_lo, b_hi = (cut, 0.0, 0.0), (ow, oh, oz)
        along_x = True
    else:
        cut = oh / 2.0
        seats = [(t.wall_mm / 2.0, cut, z), (ow - t.wall_mm / 2.0, cut, z)]
        a_lo, a_hi = (0.0, 0.0, 0.0), (ow, cut, oz)
        b_lo, b_hi = (0.0, cut, 0.0), (ow, oh, oz)
        along_x = False

    half_a = _half(tray, a_lo, a_hi)
    half_b = _half(tray, b_lo, b_hi)

    # Pins protrude from half A into matching clearance holes in half B.
    pins = [_pin(r, L, along_x, c) for c in seats]
    holes = [_pin(hole_r, L + 1.0, along_x, c) for c in seats]
    half_a = trimesh.boolean.union([half_a, *pins], engine="manifold")
    half_b = trimesh.boolean.difference([half_b, *holes], engine="manifold")
    half_a.fix_normals()
    half_b.fix_normals()

    # Report whether each printed half now fits.
    parts = [("tray-half-A", half_a), ("tray-half-B", half_b)]
    for name, mesh in parts:
        ex, ey = mesh.extents[0], mesh.extents[1]
        if ex > bv.x_mm or ey > bv.y_mm:
            warnings.append(f"{name} is {ex:.0f}×{ey:.0f} mm — still exceeds the plate")
    return parts, warnings
