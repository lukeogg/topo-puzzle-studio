"""Tier-3 OSM feature overlays: drape roads/trails/waterways/lakes onto terrain.

Features arrive in lon/lat (:class:`~topopuzzle_mesh.providers.osm.OsmFeature`).
Here they are:

1. transformed into model XY (mm) using the terrain's UTM grid bounds,
2. buffered to ribbons (lines) or kept as footprints (lakes), sized from a
   per-class real-world width and dropped below the printable minimum,
3. clipped to the model footprint, then
4. either **baked into the terrain heightfield** (deboss/emboss — recess or raise
   the surface) or **built as flush inlay objects** via a top-shell.

Baking into the heightfield *before* the puzzle split means grooves are inherited
by every piece and clipped at seams for free, and the result stays watertight.
Grooves are clamped so they never cut into the base slab, which keeps connector
walls intact (a shallow top-surface groove cannot sever a full-height tab neck).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from .config import OverlayClass, OverlaySettings, RenderMode

# Per-class real-world ribbon width (m) for line features; lakes are polygons.
CLASS_WIDTH_M = {
    OverlayClass.ROADS: 12.0,
    OverlayClass.TRAILS: 1.5,
    OverlayClass.WATERWAYS: 6.0,
}
CLASS_HEX = {
    OverlayClass.ROADS: "#4d4d4d",
    OverlayClass.TRAILS: "#8a5a2b",
    OverlayClass.WATERWAYS: "#2f6fb0",
    OverlayClass.LAKES: "#2f6fb0",
}


@dataclass
class Ribbon:
    poly: Polygon  # model-space footprint (mm)
    osm_class: OverlayClass
    hex: str


def _to_model_xy(coords, grid, width_mm: float, height_mm: float):
    """Map lon/lat vertices to model XY (mm) via the grid's UTM bounds."""
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", grid.crs, always_xy=True)
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    gx, gy = tr.transform(lons, lats)
    w, s, e, n = grid.bounds
    dw = (e - w) or 1.0
    dh = (n - s) or 1.0
    return [((x - w) / dw * width_mm, (y - s) / dh * height_mm) for x, y in zip(gx, gy)]


def features_to_ribbons(
    features, grid, width_mm: float, height_mm: float, horizontal_scale: float, ov: OverlaySettings
) -> tuple[list[Ribbon], list[str]]:
    """Build clipped model-space ribbons and any drop/attribution warnings."""
    footprint = box(0.0, 0.0, width_mm, height_mm)
    ribbons: list[Ribbon] = []
    dropped: dict[OverlayClass, float] = {}
    wanted = set(ov.classes)

    for f in features:
        if f.osm_class not in wanted:
            continue
        pts = _to_model_xy(f.coords, grid, width_mm, height_mm)
        hexc = CLASS_HEX.get(f.osm_class, "#666666")
        if f.geom_type == "polygon":
            if len(pts) < 3:
                continue
            poly = Polygon(pts)
            if not poly.is_valid:
                poly = poly.buffer(0)
            geom = poly.intersection(footprint)
        else:
            if len(pts) < 2:
                continue
            ribbon_mm = CLASS_WIDTH_M.get(f.osm_class, 3.0) * horizontal_scale * ov.width_scale
            if ribbon_mm < ov.min_width_mm:
                dropped[f.osm_class] = ribbon_mm
                continue
            geom = LineString(pts).buffer(ribbon_mm / 2.0, cap_style=2).intersection(footprint)
        if geom.is_empty or geom.area <= 0:
            continue
        for g in getattr(geom, "geoms", [geom]):
            if isinstance(g, Polygon) and g.area > 0:
                ribbons.append(Ribbon(poly=g, osm_class=f.osm_class, hex=hexc))

    warnings = [
        f"overlay class '{c.value}' dropped: ribbon {w:.2f} mm below the "
        f"{ov.min_width_mm} mm minimum at this scale (increase size or width_scale)"
        for c, w in dropped.items()
    ]
    return ribbons, warnings


def _rasterize(region, x_mm: np.ndarray, y_mm: np.ndarray) -> np.ndarray:
    """Boolean grid mask (rows, cols) of cells whose centre falls in ``region``."""
    from matplotlib.path import Path

    X, Y = np.meshgrid(x_mm, y_mm)  # (rows, cols), row 0 = north
    pts = np.column_stack([X.ravel(), Y.ravel()])
    mask = np.zeros(pts.shape[0], dtype=bool)
    polys = getattr(region, "geoms", [region])
    for poly in polys:
        if not isinstance(poly, Polygon) or poly.area <= 0:
            continue
        path = Path(np.asarray(poly.exterior.coords))
        mask |= path.contains_points(pts)
        for hole in poly.interiors:
            mask &= ~Path(np.asarray(hole.coords)).contains_points(pts)
    return mask.reshape(X.shape)


def bake_surface_overlays(
    z_mm: np.ndarray,
    x_mm: np.ndarray,
    y_mm: np.ndarray,
    ribbons: list[Ribbon],
    ov: OverlaySettings,
    base_mm: float,
) -> np.ndarray:
    """Return a copy of ``z_mm`` with deboss/emboss (or inlay groove) applied.

    Deboss and inlay recess the surface (clamped to the base top so grooves never
    breach the base); emboss raises it.
    """
    if not ribbons:
        return z_mm
    region = unary_union([r.poly for r in ribbons])
    if region.is_empty:
        return z_mm
    mask = _rasterize(region, x_mm, y_mm)
    if not mask.any():
        return z_mm
    out = z_mm.copy()
    if ov.render is RenderMode.EMBOSS:
        out[mask] = out[mask] + ov.relief_mm
    else:  # DEBOSS or INLAY groove
        out[mask] = np.maximum(out[mask] - ov.relief_mm, base_mm)
    return out


def apply_overlays(terrain, features, settings):
    """Drape ``features`` onto ``terrain``.

    Returns ``(terrain, inlay_regions, warnings)``:

    * deboss / emboss are **baked into the heightfield** (the returned terrain has
      an updated solid) and ``inlay_regions`` is empty.
    * inlay leaves the surface unchanged and returns ``inlay_regions`` — a list of
      ``(name, polygon, hex)`` for per-piece flush top-shell partitioning (a flush
      inlay is a colour split, not a geometry change).
    """
    import dataclasses

    from .terrain import heightfield_solid

    ov = settings.overlays
    ribbons, warnings = features_to_ribbons(
        features, terrain.grid, terrain.width_mm, terrain.height_mm,
        terrain.horizontal_scale, ov,
    )
    if not ribbons:
        return terrain, [], warnings

    if ov.render is RenderMode.INLAY:
        regions = [
            (f"inlay-{r.osm_class.value}-{i}", r.poly, r.hex) for i, r in enumerate(ribbons)
        ]
        return terrain, regions, warnings

    z2 = bake_surface_overlays(
        terrain.z_mm, terrain.x_mm, terrain.y_mm, ribbons, ov, terrain.base_mm
    )
    new_mesh = heightfield_solid(z2, terrain.x_mm, terrain.y_mm)
    terrain = dataclasses.replace(terrain, mesh=new_mesh, z_mm=z2)
    return terrain, [], warnings
