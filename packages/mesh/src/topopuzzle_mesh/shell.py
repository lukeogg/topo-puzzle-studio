"""Top-shell extraction — the surface-following ``depth``-thick skin of a solid
over a 2-D region.

Used by inlay overlays (Tier-3) and land-cover colouring (Tier-4): both need the
top few tenths of a millimetre of the terrain over some footprint, following the
surface exactly, as its own watertight object.  Built purely by CSG so it stays
manifold: ``(solid ∩ column) − (solid↓depth ∩ column)``.
"""

from __future__ import annotations

import trimesh
from shapely.geometry import MultiPolygon, Polygon


def _polys(geom) -> list[Polygon]:
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if g.area > 0]
    if isinstance(geom, Polygon) and geom.area > 0:
        return [geom]
    return []


def _tall_prism(poly: Polygon, z_lo: float, z_hi: float) -> trimesh.Trimesh:
    m = trimesh.creation.extrude_polygon(poly, height=z_hi - z_lo)
    m.apply_translation((0, 0, z_lo))
    return m


def top_shell(
    solid: trimesh.Trimesh, region, depth: float, *, engine: str = "manifold"
) -> trimesh.Trimesh | None:
    """The top ``depth`` mm of ``solid`` clipped to ``region`` (a shapely polygon
    or multipolygon), following the surface.  Returns None if empty."""
    polys = _polys(region)
    if not polys or depth <= 0:
        return None
    b = solid.bounds
    z_lo, z_hi = float(b[0][2]) - 1.0, float(b[1][2]) + 1.0

    low = solid.copy()
    low.apply_translation((0.0, 0.0, -depth))

    shells: list[trimesh.Trimesh] = []
    for poly in polys:
        prism = _tall_prism(poly, z_lo, z_hi)
        col = trimesh.boolean.intersection([solid, prism], engine=engine)
        if col.is_empty or len(col.faces) == 0:
            continue
        low_col = trimesh.boolean.intersection([low, prism], engine=engine)
        shell = trimesh.boolean.difference([col, low_col], engine=engine)
        if not shell.is_empty and len(shell.faces) > 0:
            shells.append(shell)
    if not shells:
        return None
    out = shells[0] if len(shells) == 1 else trimesh.util.concatenate(shells)
    out.fix_normals()
    return out
