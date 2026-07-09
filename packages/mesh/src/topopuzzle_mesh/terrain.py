"""Build a watertight terrain solid from an elevation grid.

The solid is a closed heightfield: a triangulated top surface, a flat bottom at
``z = 0``, and vertical side walls joining their perimeters.  Sharing the
perimeter vertices between the top/bottom surfaces and the walls guarantees the
result is watertight and manifold, which every export must satisfy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

from . import dem as demmod
from .config import GenerateSettings
from .elevation import ElevationGrid


@dataclass
class TerrainResult:
    mesh: trimesh.Trimesh
    width_mm: float  # X extent (east-west)
    height_mm: float  # Y extent (north-south)
    z_mm: np.ndarray  # top heightfield in mm, shape (rows, cols)
    x_mm: np.ndarray  # column x-coordinates, shape (cols,)
    y_mm: np.ndarray  # row y-coordinates, shape (rows,)
    horizontal_scale: float  # mm per ground-metre
    base_mm: float
    max_slope_deg: float  # steepest local slope after exaggeration
    grid: ElevationGrid  # the processed grid used
    nodata_fraction: float  # fraction of source cells that were interpolated


def heightfield_solid(
    z_mm: np.ndarray, x_mm: np.ndarray, y_mm: np.ndarray
) -> trimesh.Trimesh:
    """Close a heightfield into a watertight solid with a flat ``z=0`` bottom."""
    rows, cols = z_mm.shape
    assert x_mm.shape == (cols,) and y_mm.shape == (rows,)

    X, Y = np.meshgrid(x_mm, y_mm)  # (rows, cols)
    top = np.column_stack([X.ravel(), Y.ravel(), z_mm.ravel()])
    bot = np.column_stack([X.ravel(), Y.ravel(), np.zeros(rows * cols)])
    vertices = np.vstack([top, bot])
    n = rows * cols  # bottom vertex offset

    def vid(i, j):
        return i * cols + j

    # --- top & bottom surfaces (vectorized over cells) ---
    ii, jj = np.meshgrid(np.arange(rows - 1), np.arange(cols - 1), indexing="ij")
    a = (ii * cols + jj).ravel()
    b = (ii * cols + jj + 1).ravel()
    c = ((ii + 1) * cols + jj + 1).ravel()
    d = ((ii + 1) * cols + jj).ravel()
    top_faces = np.vstack([np.column_stack([a, b, d]), np.column_stack([b, c, d])])
    # Bottom faces reuse the same cells, shifted to bottom verts, reverse winding.
    bot_faces = np.vstack(
        [np.column_stack([a + n, d + n, b + n]), np.column_stack([b + n, d + n, c + n])]
    )

    # --- side walls around the perimeter ---
    wall = []

    def quad(t0, t1):
        # top edge t0->t1, closed to the bottom ring below it.
        wall.append((t0, t1, t1 + n))
        wall.append((t0, t1 + n, t0 + n))

    for j in range(cols - 1):  # north edge (i=0)
        quad(vid(0, j + 1), vid(0, j))
    for j in range(cols - 1):  # south edge (i=rows-1)
        quad(vid(rows - 1, j), vid(rows - 1, j + 1))
    for i in range(rows - 1):  # west edge (j=0)
        quad(vid(i, 0), vid(i + 1, 0))
    for i in range(rows - 1):  # east edge (j=cols-1)
        quad(vid(i + 1, cols - 1), vid(i, cols - 1))

    faces = np.vstack([top_faces, bot_faces, np.array(wall, dtype=np.int64)])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    mesh.fix_normals()
    return mesh


def _max_slope_deg(z_mm: np.ndarray, dx: float, dy: float) -> float:
    """Steepest local slope of the heightfield, in degrees."""
    gy, gx = np.gradient(z_mm, dy, dx)
    slope = np.sqrt(gx**2 + gy**2)
    return float(np.degrees(np.arctan(slope.max())))


def build_terrain(grid: ElevationGrid, settings: GenerateSettings) -> TerrainResult:
    """Run the full raster→solid pipeline for a single (un-split) terrain block."""
    # Cells the *provider* could not supply.  Measured before the warp, whose
    # unmapped corners are an artifact of rotating a lon/lat quad into UTM
    # rather than missing data.
    nodata_fraction = grid.nodata_fraction
    # 1. Project to true metres so dimensions are honest.
    g = demmod.reproject_to_utm(grid)
    # 2. Fill nodata *before* resampling — the warp leaves unmapped corner cells
    #    and a bilinear downsample would smear them into valid terrain.
    g, _ = demmod.fill_nodata(g)
    # 3. Resample to the target mesh resolution, then smooth / flatten water.
    g = demmod.resample_to_max(g, settings.max_grid)
    g = demmod.gaussian_smooth(g, settings.smoothing_sigma)
    if settings.water.enabled:
        g = demmod.flatten_water(g, settings.water.threshold_m)

    # 4. Physical footprint from true ground extent, longest edge = size_mm.
    gw_m, gh_m = demmod.ground_extent_m(g)
    longest_m = max(gw_m, gh_m)
    horizontal_scale = settings.size_mm / longest_m
    width_mm = gw_m * horizontal_scale
    height_mm = gh_m * horizontal_scale

    rows, cols = g.shape
    x_mm = np.linspace(0.0, width_mm, cols)
    y_mm = np.linspace(height_mm, 0.0, rows)  # row 0 = north = max Y

    z_mm = demmod.normalize_z(
        g.values,
        horizontal_scale=horizontal_scale,
        z_exaggeration=settings.z_exaggeration,
        base_mm=settings.base_mm,
    )
    if settings.water.enabled and settings.water.recess_mm > 0:
        # Recess the flat water surface below the surrounding base top.
        water_z = z_mm.min()
        is_water = g.values <= settings.water.threshold_m + 1e-6
        z_mm[is_water] = np.maximum(
            settings.base_mm * 0.25, water_z - settings.water.recess_mm
        )

    dx = width_mm / max(cols - 1, 1)
    dy = height_mm / max(rows - 1, 1)
    max_slope = _max_slope_deg(z_mm, dx, dy)

    mesh = heightfield_solid(z_mm, x_mm, y_mm)
    return TerrainResult(
        mesh=mesh,
        width_mm=width_mm,
        height_mm=height_mm,
        z_mm=z_mm,
        x_mm=x_mm,
        y_mm=y_mm,
        horizontal_scale=horizontal_scale,
        base_mm=settings.base_mm,
        max_slope_deg=max_slope,
        grid=g,
        nodata_fraction=nodata_fraction,
    )
