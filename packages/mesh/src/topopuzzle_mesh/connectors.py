"""Original, parametric tab/socket connector geometry.

Connectors are built in 2-D (the XY footprint plane) as shapely polygons that
straddle a seam line.  A tab is *added* to one piece and the identical shape is
*subtracted* from its neighbour, so the two footprints always tessellate exactly
— no gaps, no overlaps — before any clearance/gap offset is applied.

Two profiles:

* ``straight-tab`` — a rectangular, straight-walled tab.  No undercut, so it is
  safe for print-in-place (won't fuse layer-to-layer).
* ``rounded-tab`` — a jigsaw knob (neck + disc) with a gentle undercut for a
  mechanical hold.  Separate-pieces only.

All geometry is original and derives purely from the parameters below.
"""

from __future__ import annotations

import numpy as np
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

from .config import ConnectorSettings, ConnectorStyle


def _straight_tab(width: float, depth: float, root_overlap: float) -> Polygon:
    """A rectangular tab rooted at x=0, protruding to +x by ``depth``.

    ``root_overlap`` extends the tab slightly back across the seam so a union
    with the owning piece merges without a hairline artifact.
    """
    w = width / 2.0
    # Slight draft so the very tip is a touch narrower — helps insertion and
    # avoids a perfectly vertical print wall at the corners.
    tip = w * 0.92
    return Polygon(
        [
            (-root_overlap, -w),
            (depth * 0.55, -w),
            (depth, -tip),
            (depth, tip),
            (depth * 0.55, w),
            (-root_overlap, w),
        ]
    )


def _rounded_tab(width: float, depth: float, root_overlap: float) -> Polygon:
    """A jigsaw-style knob: a narrow neck opening into a disc (mild undercut)."""
    neck = width * 0.45
    r = width * 0.5
    cx = depth - r  # disc centre so the knob reaches x=depth
    cx = max(cx, neck)  # keep the disc ahead of the neck
    # Neck rectangle from the seam to the disc centre.
    neck_poly = Polygon(
        [
            (-root_overlap, -neck / 2),
            (cx, -neck / 2),
            (cx, neck / 2),
            (-root_overlap, neck / 2),
        ]
    )
    ang = np.linspace(-np.pi, np.pi, 40)
    disc = Polygon(np.column_stack([cx + r * np.cos(ang), r * np.sin(ang)]))
    return neck_poly.union(disc)


def _hash01(a: float, b: float, seed: int) -> float:
    """Deterministic float in [0, 1) from a seam centre + seed.

    Uses an explicit integer mix (not Python's salted ``hash``) so the same seam
    yields the same shape across processes — connectors must stay deterministic.
    """
    x = int(round(a * 1000.0)) & 0xFFFF
    y = int(round(b * 1000.0)) & 0xFFFF
    n = (x * 73856093) ^ (y * 19349663) ^ ((seed & 0xFFFF) * 83492791)
    n &= 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 0x5BD1E995) & 0xFFFFFFFF
    n ^= n >> 15
    return (n & 0xFFFFFF) / float(0x1000000)


def _organic_tab(width: float, depth: float, root_overlap: float, jitter: float) -> Polygon:
    """A seeded, blobby knob: a neck opening into an irregular lobe (undercut).

    The lobe radius is modulated by a seeded sinusoid so every seam looks a little
    different — an organic, hand-cut feel — while staying deterministic.
    """
    neck = width * 0.5
    r = width * 0.5
    cx = max(depth - r, neck)
    neck_poly = Polygon(
        [
            (-root_overlap, -neck / 2),
            (cx, -neck / 2),
            (cx, neck / 2),
            (-root_overlap, neck / 2),
        ]
    )
    ang = np.linspace(-np.pi, np.pi, 48, endpoint=False)
    amp = 0.12 + 0.10 * jitter
    phase = 2.0 * np.pi * jitter
    rr = r * (1.0 + amp * np.sin(3.0 * ang + phase))
    lobe = Polygon(np.column_stack([cx + rr * np.cos(ang), rr * np.sin(ang)]))
    out = neck_poly.union(lobe)
    return out.geoms[0] if out.geom_type == "MultiPolygon" else out


def _voronoi_tab(width: float, depth: float, root_overlap: float, jitter: float) -> Polygon:
    """A seeded, faceted cell knob: a neck into a straight-edged polygon (undercut).

    Straight facets give a Voronoi-cell look; the facet count/rotation vary with
    the seed.  The widest facets sit past the neck, so it holds like a knob.
    """
    neck = width * 0.5
    r = width * 0.55
    cx = max(depth - r, neck)
    neck_poly = Polygon(
        [
            (-root_overlap, -neck / 2),
            (cx, -neck / 2),
            (cx, neck / 2),
            (-root_overlap, neck / 2),
        ]
    )
    n = 5 + int(round(jitter))  # 5 or 6 facets
    rot = 2.0 * np.pi * jitter
    ang = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False) + rot
    rr = r * (0.85 + 0.25 * np.abs(np.sin(3.0 * ang)))
    cell = Polygon(np.column_stack([cx + rr * np.cos(ang), rr * np.sin(ang)]))
    out = neck_poly.union(cell)
    return out.geoms[0] if out.geom_type == "MultiPolygon" else out


def tab_polygon(
    settings: ConnectorSettings,
    *,
    edge_length: float,
    seam_is_vertical: bool,
    center: tuple[float, float],
    into_positive: bool,
) -> Polygon:
    """Build a tab polygon straddling a seam.

    Parameters
    ----------
    edge_length: length of the shared edge (used to size the tab width).
    seam_is_vertical: True if the seam runs along Y (a vertical grid line).
    center: the (x, y) midpoint of the shared edge, where the tab is centred.
    into_positive: True if the tab protrudes toward +x (vertical seam) or +y
        (horizontal seam); False protrudes the other way.
    """
    width = min(settings.width_frac * edge_length, edge_length * 0.7)
    depth = settings.depth_mm
    root_overlap = min(depth * 0.15, 0.5)

    if settings.style is ConnectorStyle.STRAIGHT_TAB:
        base = _straight_tab(width, depth, root_overlap)
    elif settings.style is ConnectorStyle.ORGANIC_TAB:
        base = _organic_tab(width, depth, root_overlap, _hash01(*center, settings.seed))
    elif settings.style is ConnectorStyle.VORONOI_TAB:
        base = _voronoi_tab(width, depth, root_overlap, _hash01(*center, settings.seed))
    else:
        base = _rounded_tab(width, depth, root_overlap)

    # base is built rooted at x=0 protruding +x, centred on y=0.
    if not into_positive:
        base = rotate(base, 180, origin=(0, 0))
    if not seam_is_vertical:
        # Rotate so protrusion is along Y instead of X.
        base = rotate(base, 90, origin=(0, 0))
    return translate(base, xoff=center[0], yoff=center[1])
