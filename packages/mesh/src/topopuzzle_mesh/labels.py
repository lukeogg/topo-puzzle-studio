"""Embossed underside labels ("A1", "B3", …).

Glyph outlines come from matplotlib's ``TextPath`` (clean vector polygons, no
bitmap blockiness), are converted to shapely polygons, extruded into a thin
prism, and subtracted from the bottom of a piece so the label reads correctly
when the piece is flipped over.
"""

from __future__ import annotations

import numpy as np
import trimesh
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from shapely.geometry import Polygon
from shapely.ops import unary_union


def _text_polygons(text: str, size_mm: float) -> list[Polygon]:
    """Return filled glyph polygons for ``text`` at cap-height ~= ``size_mm``."""
    fp = FontProperties(family="DejaVu Sans", weight="bold")
    tp = TextPath((0, 0), text, size=size_mm, prop=fp)
    polys: list[Polygon] = []
    for poly in tp.to_polygons():
        if len(poly) >= 3:
            polys.append(Polygon(poly))
    # Resolve holes (e.g. the counter of an 'A'/'B') via even-odd union.
    merged = unary_union([p if p.is_valid else p.buffer(0) for p in polys])
    if merged.geom_type == "Polygon":
        return [merged]
    return list(merged.geoms)


def emboss_label(
    mesh: trimesh.Trimesh,
    text: str,
    *,
    depth_mm: float = 0.6,
    height_mm: float = 6.0,
    engine: str = "manifold",
) -> trimesh.Trimesh:
    """Recess ``text`` into the flat bottom (z=0) of ``mesh``.

    The label is mirrored in X so it is readable when the piece is turned over,
    and centred on the piece footprint.
    """
    polys = _text_polygons(text, height_mm)
    if not polys:
        return mesh
    group = unary_union(polys)
    minx, miny, maxx, maxy = group.bounds
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0

    bmin, bmax = mesh.bounds
    pcx, pcy = (bmin[0] + bmax[0]) / 2.0, (bmin[1] + bmax[1]) / 2.0

    stamp = None
    for p in (polys if group.geom_type != "Polygon" else [group]):
        prism = trimesh.creation.extrude_polygon(p, height=depth_mm + 0.2)
        stamp = prism if stamp is None else trimesh.util.concatenate([stamp, prism])

    # Mirror in X (readable from below), move label centre to piece centre,
    # and sink it just below z=0 so it cuts into the base.
    stamp.apply_transform(np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]))
    stamp.apply_translation((pcx + cx, pcy - cy, -0.1))

    out = trimesh.boolean.difference([mesh, stamp], engine=engine)
    out.fix_normals()
    return out
