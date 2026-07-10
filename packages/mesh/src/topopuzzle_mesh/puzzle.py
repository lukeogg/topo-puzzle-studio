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
    #: Tier-2 contour slabs, per piece, as (name, mesh, hex). Complete partition.
    banded_objects: list = field(default_factory=list)
    #: Tier-3 flush inlay ribbons + base, per piece, as (name, mesh, hex).
    overlay_objects: list = field(default_factory=list)
    #: Tier-4 land-cover shells + base, per piece, as (name, mesh, hex).
    landcover_objects: list = field(default_factory=list)
    #: Tray part(s) ready to export as (name, mesh).
    tray_parts: list = field(default_factory=list)
    #: Extra attribution blocks (e.g. land-cover licence) for the manifest.
    extra_attributions: list = field(default_factory=list)

    @property
    def assembled_footprint_mm(self) -> tuple[float, float]:
        return (self.terrain.width_mm, self.terrain.height_mm)

    @property
    def color_objects(self) -> list:
        """All Tier-2/3/4 colour objects (for validation and export)."""
        return self.banded_objects + self.overlay_objects + self.landcover_objects


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


def _finalize_piece(mesh, piece, settings, warnings):
    """Bake underside label + magnet pocket into a piece so the shipped mesh is
    what gets validated (labels skipped for a single solid model)."""
    if settings.labels and not settings.is_solid:
        try:
            from .labels import emboss_label

            mesh = emboss_label(
                mesh, piece.label, depth_mm=settings.label_depth_mm,
                height_mm=max(6.0, min(mesh.extents[0], mesh.extents[1]) * 0.25),
            )
        except Exception as exc:  # noqa: BLE001 - label is cosmetic; record why
            warnings.append(f"piece {piece.label}: label skipped ({exc})")
    if settings.magnets.enabled:
        try:
            from .magnets import add_magnet_pockets

            mesh, warn = add_magnet_pockets(mesh, piece.fit_footprint, settings.magnets, settings.base_mm)
            if warn:
                warnings.append(warn)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"piece {piece.label}: magnet pocket skipped ({exc})")
    return mesh


def split_puzzle(
    grid: ElevationGrid, settings: GenerateSettings, features=None, landcover=None
) -> PuzzleResult:
    """Full split: terrain → overlays → tessellation → per-piece CSG → finalize →
    per-piece colour objects → tray. Every mesh returned here is export-final, so
    validation covers exactly what ships."""
    terrain = build_terrain(grid, settings)
    warnings: list[str] = []
    extra_attributions: list = []

    # Tier-3 deboss/emboss are baked into the terrain solid before splitting so
    # every piece inherits the grooves clipped at its seams. Inlay stays flush and
    # comes back as 2-D regions for per-piece top-shell partitioning below.
    inlay_regions: list = []
    if settings.overlays.enabled and features:
        from .overlays import apply_overlays

        terrain, inlay_regions, ov_warns = apply_overlays(terrain, features, settings)
        warnings.extend(ov_warns)

    # --- build raw pieces ---
    if settings.is_solid:
        pieces = [Piece(
            row=0, col=0, label="A1",
            footprint=box(0, 0, terrain.width_mm, terrain.height_mm),
            fit_footprint=box(0, 0, terrain.width_mm, terrain.height_mm),
            mesh=terrain.mesh,
        )]
    else:
        tess = build_tessellation(terrain, settings)
        offset = (settings.gap_mm if settings.assembly is AssemblyMode.PRINT_IN_PLACE
                  else settings.connector.clearance_mm) / 2.0
        z_lo, z_hi = -1.0, float(terrain.z_mm.max()) + 1.0
        pieces = []
        for (r, c), poly in sorted(tess.items()):
            fit = _largest(poly.buffer(-offset, join_style=2)) if offset > 0 else poly
            if fit.is_empty or fit.area <= 0:
                warnings.append(f"piece {piece_label(r, c)} collapsed under the clearance/gap offset")
                continue
            mesh = trimesh.boolean.intersection([terrain.mesh, _prism(fit, z_lo, z_hi)], engine="manifold")
            if mesh.is_empty or len(mesh.faces) == 0:
                warnings.append(f"piece {piece_label(r, c)} produced an empty mesh")
                continue
            mesh.fix_normals()
            pieces.append(Piece(r, c, piece_label(r, c), poly, fit, mesh))

    # --- finalize (labels + magnets) so validation sees the shipped meshes ---
    for p in pieces:
        p.mesh = _finalize_piece(p.mesh, p, settings, warnings)

    # --- per-piece colour objects (complete, non-overlapping partitions) ---
    banded_objects, overlay_objects, landcover_objects = [], [], []

    if settings.contour_bands and settings.bands:
        from .coloring import contour_partition
        from .contour import band_z_cuts

        bands, cuts, band_lo = band_z_cuts(terrain, settings)
        if cuts[-1] > 0 and len(cuts) >= 2:
            for p in pieces:
                objs, w = contour_partition(p.mesh, p.label, bands, cuts, band_lo)
                banded_objects.extend(objs)
                warnings.extend(w)

    if inlay_regions:
        from .coloring import top_shell_partition

        for p in pieces:
            objs, w = top_shell_partition(p.mesh, p.label, inlay_regions, settings.overlays.relief_mm)
            overlay_objects.extend(objs)
            warnings.extend(w)

    if settings.landcover.enabled and landcover is not None:
        from .coloring import top_shell_partition
        from .landcover import landcover_regions

        regions, lc_warns, lc_attr = landcover_regions(terrain, landcover, settings)
        warnings.extend(lc_warns)
        if lc_attr is not None:
            extra_attributions.append(lc_attr)
        for p in pieces:
            objs, w = top_shell_partition(p.mesh, p.label, regions, settings.landcover.shell_mm)
            landcover_objects.extend(objs)
            warnings.extend(w)

    # --- tray part(s), built here so they are validated too ---
    tray_parts: list = []
    if settings.tray.enabled:
        try:
            from .tray import split_tray

            tray_parts, tray_warns = split_tray(terrain, settings)
            warnings.extend(tray_warns)
        except Exception as exc:  # noqa: BLE001 - tray is optional; surface why
            warnings.append(f"tray generation failed: {exc}")

    return PuzzleResult(
        pieces, terrain, settings, warnings,
        banded_objects, overlay_objects, landcover_objects, tray_parts, extra_attributions,
    )
