"""Split a terrain solid into an interlocking grid puzzle.

The pipeline:

1. Build the exact footprint tessellation — each cell is a shapely polygon whose
   internal seams carry connectors.  A tab added to one cell is subtracted from
   its neighbour, so the cells tile the footprint perfectly.
2. Derive the *fit* footprint per assembly mode: shrink each cell by
   ``clearance/2`` (separate-pieces, symmetric friction fit) or ``gap/2``
   (print-in-place, a printable separation gap on every seam).
3. Extrude each fit footprint into a tall prism and intersect it with the
   terrain solid via manifold3d — the intersection of two watertight solids is
   itself watertight, so every piece is guaranteed printable.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field

import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon, box

from . import connectors
from .config import AssemblyMode, ConnectorStyle, GenerateSettings
from .elevation import ElevationGrid
from .terrain import TerrainResult, build_terrain


def piece_label(row: int, col: int) -> str:
    """Row letter (A, B, …, Z, AA) + 1-based column, e.g. ``A1``, ``C3``."""
    letters = string.ascii_uppercase
    if row < 26:
        rl = letters[row]
    else:
        rl = letters[row // 26 - 1] + letters[row % 26]
    return f"{rl}{col + 1}"


@dataclass
class Piece:
    row: int
    col: int
    label: str
    footprint: Polygon  # exact tessellation cell (assembled coords)
    fit_footprint: Polygon  # after clearance/gap offset
    mesh: trimesh.Trimesh  # in assembled coordinates


@dataclass
class PuzzleResult:
    pieces: list[Piece]
    terrain: TerrainResult
    settings: GenerateSettings
    warnings: list[str] = field(default_factory=list)
    #: Tier-3 inlay ribbons as (name, mesh, hex) — assembled coords, exported to 3MF.
    overlay_objects: list = field(default_factory=list)

    @property
    def assembled_footprint_mm(self) -> tuple[float, float]:
        return (self.terrain.width_mm, self.terrain.height_mm)


def _largest(poly) -> Polygon:
    """A negative buffer can split a pinched footprint; keep the biggest part."""
    if isinstance(poly, MultiPolygon):
        return max(poly.geoms, key=lambda g: g.area)
    return poly


def build_tessellation(
    terrain: TerrainResult, settings: GenerateSettings
) -> dict[tuple[int, int], Polygon]:
    """Return exact, gap-free interlocking cell polygons keyed by (row, col)."""
    rows, cols = settings.rows, settings.cols
    W, H = terrain.width_mm, terrain.height_mm
    xs = np.linspace(0.0, W, cols + 1)
    ys = np.linspace(0.0, H, rows + 1)  # ys[0]=south … ys[rows]=north

    # Row 0 is the NORTH band, so map row r to the y-band from the top.
    def y_band(r: int) -> tuple[float, float]:
        return ys[rows - 1 - r], ys[rows - r]

    polys: dict[tuple[int, int], Polygon] = {}
    for r in range(rows):
        y0, y1 = y_band(r)
        for c in range(cols):
            polys[(r, c)] = box(xs[c], y0, xs[c + 1], y1)

    seed = settings.connector.seed
    if settings.connector.style is ConnectorStyle.NONE:
        return polys

    # Vertical seams: between (r,c) and (r,c+1).
    for r in range(rows):
        y0, y1 = y_band(r)
        for c in range(cols - 1):
            x = xs[c + 1]
            owner_left = (r + c + seed) % 2 == 0
            edge_len = y1 - y0
            tab = connectors.tab_polygon(
                settings.connector,
                edge_length=edge_len,
                seam_is_vertical=True,
                center=(x, (y0 + y1) / 2.0),
                into_positive=owner_left,  # left piece pokes toward +x
            )
            left, right = (r, c), (r, c + 1)
            if owner_left:
                polys[left] = polys[left].union(tab)
                polys[right] = polys[right].difference(tab)
            else:
                polys[right] = polys[right].union(tab)
                polys[left] = polys[left].difference(tab)

    # Horizontal seams: between (r,c) and (r+1,c). Row r is north of row r+1.
    for r in range(rows - 1):
        _, y_top = y_band(r)  # shared y is the bottom of row r == top of row r+1
        y = y_top - (y_top - y_band(r)[0])  # = y_band(r)[0]
        y = y_band(r)[0]
        for c in range(cols):
            x0, x1 = xs[c], xs[c + 1]
            owner_north = (r + c + seed) % 2 == 0
            edge_len = x1 - x0
            tab = connectors.tab_polygon(
                settings.connector,
                edge_length=edge_len,
                seam_is_vertical=False,
                center=((x0 + x1) / 2.0, y),
                into_positive=False,  # north piece pokes toward -y (into south)
            )
            north, south = (r, c), (r + 1, c)
            if owner_north:
                polys[north] = polys[north].union(tab)
                polys[south] = polys[south].difference(tab)
            else:
                # Flip the tab to poke +y (into the north piece).
                tab2 = connectors.tab_polygon(
                    settings.connector,
                    edge_length=edge_len,
                    seam_is_vertical=False,
                    center=((x0 + x1) / 2.0, y),
                    into_positive=True,
                )
                polys[south] = polys[south].union(tab2)
                polys[north] = polys[north].difference(tab2)

    return {k: _largest(v) for k, v in polys.items()}


def _prism(poly: Polygon, z_lo: float, z_hi: float) -> trimesh.Trimesh:
    m = trimesh.creation.extrude_polygon(poly, height=z_hi - z_lo)
    m.apply_translation((0, 0, z_lo))
    return m


def split_puzzle(
    grid: ElevationGrid, settings: GenerateSettings, features=None
) -> PuzzleResult:
    """Full split: terrain → overlays → tessellation → per-piece CSG intersection."""
    terrain = build_terrain(grid, settings)
    warnings: list[str] = []
    overlay_objects: list = []

    # Tier-3 overlays are baked into the terrain solid before splitting, so every
    # piece inherits the grooves clipped at its own seams.
    if settings.overlays.enabled and features:
        from .overlays import apply_overlays

        terrain, overlay_objects, ov_warns = apply_overlays(terrain, features, settings)
        warnings.extend(ov_warns)

    if settings.is_solid:
        piece = Piece(
            row=0,
            col=0,
            label="A1",
            footprint=box(0, 0, terrain.width_mm, terrain.height_mm),
            fit_footprint=box(0, 0, terrain.width_mm, terrain.height_mm),
            mesh=terrain.mesh,
        )
        return PuzzleResult([piece], terrain, settings, warnings, overlay_objects)

    tess = build_tessellation(terrain, settings)

    if settings.assembly is AssemblyMode.PRINT_IN_PLACE:
        offset = settings.gap_mm / 2.0
    else:
        offset = settings.connector.clearance_mm / 2.0

    z_lo = -1.0
    z_hi = float(terrain.z_mm.max()) + 1.0

    pieces: list[Piece] = []
    for (r, c), poly in sorted(tess.items()):
        fit = _largest(poly.buffer(-offset, join_style=2)) if offset > 0 else poly
        if fit.is_empty or fit.area <= 0:
            warnings.append(
                f"piece {piece_label(r, c)} collapsed under the clearance/gap offset"
            )
            continue
        prism = _prism(fit, z_lo, z_hi)
        mesh = trimesh.boolean.intersection([terrain.mesh, prism], engine="manifold")
        if mesh.is_empty or len(mesh.faces) == 0:
            warnings.append(f"piece {piece_label(r, c)} produced an empty mesh")
            continue
        mesh.fix_normals()
        pieces.append(
            Piece(
                row=r,
                col=c,
                label=piece_label(r, c),
                footprint=poly,
                fit_footprint=fit,
                mesh=mesh,
            )
        )

    return PuzzleResult(pieces, terrain, settings, warnings, overlay_objects)
