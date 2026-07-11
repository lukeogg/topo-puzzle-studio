"""Tier-2 colour: per-band contour slabs.

Where Tier 1 (``color.py``) just *tells* the slicer the Z heights at which to
swap filament, Tier 2 slices the solid into horizontal contour slabs — one
watertight object per elevation band — so bands can sit at arbitrary heights
independent of the layer height and print as distinct AMS materials.

Each band mesh is the intersection of the terrain solid with a Z-slab between two
band boundaries; intersecting two watertight solids yields a watertight solid, so
every slab is independently printable.  The slabs partition the model exactly
(shared cut planes, no gaps or overlaps).
"""

from __future__ import annotations

import numpy as np
import trimesh

from .color import elevation_to_z_mm
from .config import GenerateSettings
from .terrain import TerrainResult

_DEFAULT_RGBA = (180, 180, 180, 255)


def _hex_to_rgba(hexstr: str | None) -> tuple[int, int, int, int]:
    if not hexstr:
        return _DEFAULT_RGBA
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return _DEFAULT_RGBA
    try:
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return _DEFAULT_RGBA
    return (r, g, b, 255)


def slab_between(mesh: trimesh.Trimesh, z_lo: float, z_hi: float, *, engine: str = "manifold") -> trimesh.Trimesh | None:
    """Portion of ``mesh`` between two Z planes, via CSG with a slab box.

    Returns None if the intersection is empty (e.g. the piece has no material in
    that elevation band).
    """
    b = mesh.bounds
    pad = 1.0
    dx = (b[1][0] - b[0][0]) + 2 * pad
    dy = (b[1][1] - b[0][1]) + 2 * pad
    dz = z_hi - z_lo
    slab = trimesh.creation.box(extents=(dx, dy, dz))
    slab.apply_translation(
        (
            (b[0][0] + b[1][0]) / 2.0,
            (b[0][1] + b[1][1]) / 2.0,
            (z_lo + z_hi) / 2.0,
        )
    )
    out = trimesh.boolean.intersection([mesh, slab], engine=engine)
    if out.is_empty or len(out.faces) == 0:
        return None
    out.fix_normals()
    return out


# Back-compat alias for the assembled-solid slicer.
def _slab(mesh: trimesh.Trimesh, z_lo: float, z_hi: float) -> trimesh.Trimesh:
    return slab_between(mesh, z_lo, z_hi)


def band_z_cuts(terrain: TerrainResult, settings: GenerateSettings):
    """Return (sorted bands, cut Z planes, per-band lower Z) partitioning [0, top].

    The first band's lower edge is the base (Z=0); each subsequent band starts at
    the model Z of its ``min_m``. Cuts outside (0, top) are dropped, so collapsed
    bands merge into their neighbour rather than producing empty slabs.
    """
    top = float(terrain.z_mm.max())
    bands = sorted(settings.bands, key=lambda b: b.min_m)
    inner = []
    for b in bands[1:]:
        z = elevation_to_z_mm(b.min_m, terrain, settings)
        if 0.0 < z < top:
            inner.append(round(float(z), 6))
    cuts = [0.0] + sorted(set(inner)) + [top]
    band_lo = [0.0]
    for b in bands[1:]:
        band_lo.append(min(max(elevation_to_z_mm(b.min_m, terrain, settings), 0.0), top))
    return bands, cuts, band_lo


def contour_band_meshes(
    terrain: TerrainResult, settings: GenerateSettings
) -> list[tuple[str, trimesh.Trimesh, str | None]]:
    """Slice the assembled terrain solid into (name, mesh, hex) slabs, one per band.

    Returns an empty list when no bands are configured or the model is degenerate.
    Per-piece slicing for export goes through :func:`coloring.contour_partition`.
    """
    if not settings.bands:
        return []
    bands, cuts, band_lo = band_z_cuts(terrain, settings)
    top = cuts[-1]
    if top <= 0.0 or len(cuts) < 2:
        return []

    out: list[tuple[str, trimesh.Trimesh, str | None]] = []
    for j in range(len(cuts) - 1):
        z_lo, z_hi = cuts[j], cuts[j + 1]
        if z_hi - z_lo <= 1e-6:
            continue
        mid = (z_lo + z_hi) / 2.0
        # The band owning this interval: last band whose lower edge is <= mid.
        bi = max(i for i, lo in enumerate(band_lo) if lo <= mid + 1e-9)
        band = bands[bi]
        slab = slab_between(terrain.mesh, z_lo, z_hi)
        if slab is None:
            continue
        rgba = _hex_to_rgba(band.hex)
        slab.visual = trimesh.visual.ColorVisuals(
            slab, face_colors=np.tile(rgba, (len(slab.faces), 1))
        )
        out.append((band.name, slab, band.hex))
    return out
