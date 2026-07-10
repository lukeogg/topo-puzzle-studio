"""Magnet pockets — cylindrical blind holes recessed into a piece bottom.

The pocket opens at the flat ``z=0`` bottom face (a magnet is pressed in from
below) and rises to ``depth``, which is kept inside the base slab so the ceiling
of the pocket never breaks through the terrain surface.  Geometry is a straight-
walled cylinder subtracted via the same CSG pattern used by labels and the tray,
so a piece with pockets stays watertight and manifold.

Placement is deterministic: one pocket at the centroid of the region left after
insetting the footprint by (radius + margin), so the pocket can never breach a
wall.  If that inset region is empty (piece too small for the magnet), the pocket
is skipped and a warning is returned.
"""

from __future__ import annotations

import trimesh
from shapely.geometry import Polygon

from .config import MagnetSettings


def _safe_center(footprint: Polygon, inset: float):
    """A point guaranteed to sit ``inset`` inside the footprint, or None."""
    safe = footprint.buffer(-inset, join_style=2)
    if safe.is_empty or safe.area <= 0:
        return None
    if safe.geom_type == "MultiPolygon":
        safe = max(safe.geoms, key=lambda g: g.area)
    c = safe.centroid
    if not safe.contains(c):
        c = safe.representative_point()
    return (c.x, c.y)


def add_magnet_pockets(
    mesh: trimesh.Trimesh,
    footprint: Polygon,
    magnets: MagnetSettings,
    base_mm: float,
    *,
    engine: str = "manifold",
) -> tuple[trimesh.Trimesh, str | None]:
    """Subtract a magnet pocket from ``mesh``'s bottom. Returns (mesh, warning)."""
    if not magnets.enabled:
        return mesh, None

    radius = magnets.diameter_mm / 2.0
    # Never let the pocket reach the terrain floor: leave a printable ceiling.
    depth = min(magnets.depth_mm, max(base_mm - 0.4, 0.4))
    center = _safe_center(footprint, radius + magnets.margin_mm)
    if center is None:
        return mesh, f"magnet pocket skipped: piece too small for a {magnets.diameter_mm} mm magnet"

    # Cylinder spanning z in [-1, depth] so it cleanly opens at the bottom face.
    height = depth + 1.0
    pocket = trimesh.creation.cylinder(radius=radius, height=height, sections=48)
    pocket.apply_translation((center[0], center[1], height / 2.0 - 1.0))

    out = trimesh.boolean.difference([mesh, pocket], engine=engine)
    out.fix_normals()
    return out, None
