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
    else:
        base = _rounded_tab(width, depth, root_overlap)

    # base is built rooted at x=0 protruding +x, centred on y=0.
    if not into_positive:
        base = rotate(base, 180, origin=(0, 0))
    if not seam_is_vertical:
        # Rotate so protrusion is along Y instead of X.
        base = rotate(base, 90, origin=(0, 0))
    return translate(base, xoff=center[0], yoff=center[1])
