"""Per-piece colour partitioning shared by Tier-2/3/4 colour.

All three colour features must produce **complete, non-overlapping** objects that
partition each puzzle piece — base body plus colour regions — so a colour 3MF is
a printable multi-material model on its own, clipped to the actual pieces.

* :func:`top_shell_partition` — base body + one flush top-shell object per 2-D
  region (land-cover classes, inlay ribbons).  The shells follow the surface; the
  base is the piece with those shells removed.
* :func:`contour_partition` — horizontal elevation-band slabs of a piece (Tier-2);
  the slabs already partition the piece, so there is no separate base.

Each object is ``(name, mesh, hex)`` with ``name`` prefixed by the piece label, so
one 3MF holds every piece's coloured parts, distinguishable per piece and per
class.
"""

from __future__ import annotations

import numpy as np
import trimesh

from .shell import top_shell

#: Neutral colour for the base body / unmapped terrain.
DEFAULT_BASE_HEX = "#9a9284"


def _rgba(hexstr: str) -> tuple[int, int, int, int]:
    h = (hexstr or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (154, 146, 132, 255)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    except ValueError:
        return (154, 146, 132, 255)


def _colored(mesh: trimesh.Trimesh, hexstr: str) -> trimesh.Trimesh:
    mesh.visual = trimesh.visual.ColorVisuals(
        mesh, face_colors=np.tile(_rgba(hexstr), (len(mesh.faces), 1))
    )
    return mesh


def top_shell_partition(
    piece_mesh: trimesh.Trimesh,
    label: str,
    regions,
    depth: float,
    *,
    base_hex: str = DEFAULT_BASE_HEX,
    engine: str = "manifold",
) -> tuple[list[tuple[str, trimesh.Trimesh, str]], list[str]]:
    """Partition ``piece_mesh`` into a base body + per-region top-shells.

    ``regions`` is ``[(name, polygon, hex), …]`` in model coords.  Regions are
    clipped to the piece automatically (the shell is cut from ``piece_mesh``).
    Returns ``(objects, warnings)``.
    """
    objects: list[tuple[str, trimesh.Trimesh, str]] = []
    warnings: list[str] = []
    shells: list[trimesh.Trimesh] = []
    for name, poly, hexc in regions:
        try:
            shell = top_shell(piece_mesh, poly, depth, engine=engine)
        except Exception as exc:  # noqa: BLE001 - degrade one region, record why
            warnings.append(f"colour region '{label}-{name}' failed: {exc}")
            continue
        if shell is None or shell.is_empty or len(shell.faces) == 0:
            continue
        shells.append(shell)
        objects.append((f"{label}-{name}", _colored(shell.copy(), hexc), hexc))

    # Base body = piece minus the coloured shells (keeps the model complete).
    if shells:
        try:
            base = trimesh.boolean.difference([piece_mesh, *shells], engine=engine)
            base.fix_normals()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"colour base '{label}-base' failed: {exc}")
            base = None
    else:
        base = piece_mesh.copy()
    if base is not None and not base.is_empty and len(base.faces) > 0:
        objects.insert(0, (f"{label}-base", _colored(base, base_hex), base_hex))
    return objects, warnings


def contour_partition(
    piece_mesh: trimesh.Trimesh,
    label: str,
    bands,
    cuts,
    band_lo,
    *,
    engine: str = "manifold",
) -> tuple[list[tuple[str, trimesh.Trimesh, str]], list[str]]:
    """Slice ``piece_mesh`` into elevation-band slabs (Tier-2), named per piece.

    ``cuts`` partitions ``[0, top]`` at band boundaries; ``band_lo`` is the lower
    model-Z of each band.  Each interval is owned by the band whose lower edge is
    the greatest at or below the interval midpoint (robust to collapsed bands).
    """
    from .contour import slab_between

    objects: list[tuple[str, trimesh.Trimesh, str]] = []
    warnings: list[str] = []
    for j in range(len(cuts) - 1):
        z_lo, z_hi = cuts[j], cuts[j + 1]
        if z_hi - z_lo <= 1e-6:
            continue
        mid = (z_lo + z_hi) / 2.0
        bi = max(i for i, lo in enumerate(band_lo) if lo <= mid + 1e-9)
        band = bands[bi]
        try:
            slab = slab_between(piece_mesh, z_lo, z_hi, engine=engine)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"contour slab '{label}-{band.name}' failed: {exc}")
            continue
        if slab is None or slab.is_empty or len(slab.faces) == 0:
            continue
        objects.append((f"{label}-{band.name}", _colored(slab, band.hex or DEFAULT_BASE_HEX), band.hex))
    return objects, warnings
