"""Tier-4 land-cover surface colouring.

Colour the terrain's *top shell* by land cover using a handful of discrete
filaments (FDM can't print continuous imagery).  Steps:

1. resample the categorical land-cover raster onto the mesh grid (nearest —
   classes are categorical),
2. apply purge-waste guardrails: drop connected regions below a minimum physical
   area so tiny speckles don't force constant filament swaps,
3. map class codes → filament slots (explicit, or auto from the most common
   classes capped at one AMS's worth),
4. lift the top ``shell_mm`` of the terrain over each class's footprint as its own
   named object (via :func:`shell.top_shell`) for a per-material 3MF.

The body below the shell stays base material.  Regions are cut from the assembled
terrain solid; class boundaries crossing connectors are fine (colour only, no
geometry change).  A single-colour fallback isn't needed here — callers just skip
the extra objects.
"""

from __future__ import annotations

import numpy as np

from .providers.landcover import WORLDCOVER_LEGEND, LandCoverGrid


def resample_classes_to_mesh(landcover: LandCoverGrid, terrain) -> np.ndarray:
    """Nearest-neighbour sample of the class raster at each mesh cell centre.

    Returns an int array (rows, cols) aligned with ``terrain.z_mm``; cells outside
    the land-cover coverage are set to ``landcover.nodata``.
    """
    x_mm, y_mm = terrain.x_mm, terrain.y_mm
    X, Y = np.meshgrid(x_mm, y_mm)  # model coords, row 0 = north
    w, s, e, n = terrain.grid.bounds  # terrain grid CRS (UTM)
    gx = w + (X / max(terrain.width_mm, 1e-9)) * (e - w)
    gy = s + (Y / max(terrain.height_mm, 1e-9)) * (n - s)

    if terrain.grid.crs != landcover.crs:
        from pyproj import Transformer

        tr = Transformer.from_crs(terrain.grid.crs, landcover.crs, always_xy=True)
        gx, gy = tr.transform(gx, gy)
        gx = np.asarray(gx).reshape(X.shape)
        gy = np.asarray(gy).reshape(X.shape)

    lw, ls, le, ln = landcover.bounds
    lrows, lcols = landcover.shape
    col = ((gx - lw) / max(le - lw, 1e-9) * lcols).astype(int)
    row = ((ln - gy) / max(ln - ls, 1e-9) * lrows).astype(int)
    inside = (col >= 0) & (col < lcols) & (row >= 0) & (row < lrows)
    col = np.clip(col, 0, lcols - 1)
    row = np.clip(row, 0, lrows - 1)
    out = landcover.classes[row, col]
    out = np.where(inside, out, landcover.nodata).astype(np.int32)
    return out


def purge_filter(classes: np.ndarray, cell_area_mm2: float, min_region_mm2: float, nodata: int) -> np.ndarray:
    """Drop connected same-class regions below ``min_region_mm2`` to ``nodata``."""
    if min_region_mm2 <= 0 or cell_area_mm2 <= 0:
        return classes
    from scipy import ndimage

    min_cells = max(1, int(np.ceil(min_region_mm2 / cell_area_mm2)))
    out = classes.copy()
    for code in np.unique(classes):
        if code == nodata:
            continue
        mask = classes == code
        labels, n = ndimage.label(mask)
        if n == 0:
            continue
        sizes = ndimage.sum(np.ones_like(labels), labels, index=np.arange(1, n + 1))
        small = {i + 1 for i, sz in enumerate(sizes) if sz < min_cells}
        if small:
            drop = np.isin(labels, list(small))
            out[drop] = nodata
    return out


def _mapping(classes: np.ndarray, settings_lc, legend: dict, nodata: int) -> dict:
    """code -> (name, hex).  Explicit mapping wins; else the most common classes."""
    if settings_lc.mapping:
        m = {}
        for c in settings_lc.mapping:
            name = c.name or (legend.get(c.code, ("class", None))[0])
            hexc = c.hex or (legend.get(c.code, (None, "#888888"))[1])
            m[c.code] = (name, hexc)
        return m
    codes, counts = np.unique(classes[classes != nodata], return_counts=True)
    order = np.argsort(counts)[::-1][: settings_lc.max_classes]
    m = {}
    for code in codes[order]:
        name, hexc = legend.get(int(code), (f"class {int(code)}", "#888888"))
        m[int(code)] = (name, hexc)
    return m


def _class_region(mask: np.ndarray, x_mm: np.ndarray, y_mm: np.ndarray, width_mm: float, height_mm: float):
    """Union of masked cells as a model-space shapely geometry."""
    from affine import Affine
    from rasterio import features
    from shapely.geometry import shape
    from shapely.ops import unary_union

    rows, cols = mask.shape
    # Pixel (col,row) top-left origin at model (0, H); row increases south.
    transform = Affine(width_mm / cols, 0, 0, 0, -height_mm / rows, height_mm)
    polys = [
        shape(geom)
        for geom, val in features.shapes(mask.astype(np.uint8), mask=mask, transform=transform, connectivity=4)
        if val == 1
    ]
    if not polys:
        return None
    return unary_union(polys)


def apply_landcover(terrain, landcover: LandCoverGrid, settings):
    """Return ``(objects, warnings, attribution)`` for land-cover colouring.

    ``objects`` is a list of ``(name, mesh, hex)`` top-shell region meshes.
    """
    from .shell import top_shell

    lc = settings.landcover
    legend = landcover.legend or dict(WORLDCOVER_LEGEND)
    classes = resample_classes_to_mesh(landcover, terrain)

    dx = terrain.width_mm / max(terrain.z_mm.shape[1] - 1, 1)
    dy = terrain.height_mm / max(terrain.z_mm.shape[0] - 1, 1)
    classes = purge_filter(classes, dx * dy, lc.min_region_mm2, landcover.nodata)

    mapping = _mapping(classes, lc, legend, landcover.nodata)
    objects: list[tuple[str, object, str]] = []
    region_count = 0
    import trimesh

    for code, (name, hexc) in mapping.items():
        mask = classes == code
        if not mask.any():
            continue
        region = _class_region(mask, terrain.x_mm, terrain.y_mm, terrain.width_mm, terrain.height_mm)
        if region is None:
            continue
        shell = top_shell(terrain.mesh, region, lc.shell_mm)
        if shell is None:
            continue
        region_count += len(getattr(region, "geoms", [region]))
        rgba = _hex_rgba(hexc)
        shell.visual = trimesh.visual.ColorVisuals(shell, face_colors=np.tile(rgba, (len(shell.faces), 1)))
        slug = name.replace(" ", "-").replace("/", "")
        objects.append((f"landcover-{slug}-{code}", shell, hexc))

    warnings: list[str] = []
    k = len(objects)
    if k:
        warnings.append(
            f"land cover: {k} filament class(es) across {region_count} region(s) in the "
            f"top {lc.shell_mm} mm — expect up to {max(k - 1, 0)} colour change(s) per shell "
            "layer and some purge waste."
        )
        if region_count > 40:
            warnings.append(
                f"land cover: {region_count} disjoint regions — heavy purge waste/print time; "
                "raise min_region_mm2 or reduce classes."
            )
    return objects, warnings, landcover.attribution


def _hex_rgba(hexstr: str) -> tuple[int, int, int, int]:
    h = (hexstr or "").lstrip("#")
    if len(h) != 6:
        return (150, 150, 150, 255)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    except ValueError:
        return (150, 150, 150, 255)
