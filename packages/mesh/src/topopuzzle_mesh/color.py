"""Tier-1 colour: elevation-band → Z-height mapping.

FDM models get colour from the slicer.  This emits a ``color-changes.txt`` that
tells the user the exact model Z (in mm) at which each elevation band begins, so
they can add an AMS filament change at that height in Bambu Studio in seconds.
"""

from __future__ import annotations

from .config import GenerateSettings
from .terrain import TerrainResult


def elevation_to_z_mm(elev_m: float, terrain: TerrainResult, settings: GenerateSettings) -> float:
    """Model Z (mm) for a real-world elevation, matching ``dem.normalize_z``."""
    elev_min = float(terrain.grid.values.min())
    return settings.base_mm + (elev_m - elev_min) * terrain.horizontal_scale * settings.z_exaggeration


def color_changes_text(terrain: TerrainResult, settings: GenerateSettings, layer_mm: float = 0.2) -> str:
    """Render the color-changes.txt body for the configured bands."""
    lines = [
        "# TopoPuzzle Studio — AMS colour changes",
        "# Add a filament change at each Z height below (Bambu Studio: right-click the",
        f"# layer at the given height). Layer numbers assume a {layer_mm:.2f} mm layer height.",
        f"# base thickness: {settings.base_mm:.2f} mm   vertical exaggeration: {settings.z_exaggeration:.2f}x",
        "",
    ]
    if not settings.bands:
        lines.append("# (no elevation bands configured)")
        return "\n".join(lines) + "\n"

    bands = sorted(settings.bands, key=lambda b: b.min_m)
    lines.append(f"{'elevation_m':>12}  {'z_mm':>8}  {'layer':>6}  name")
    for b in bands:
        z = elevation_to_z_mm(b.min_m, terrain, settings)
        z = max(z, settings.base_mm)
        layer = max(1, round(z / layer_mm))
        hexs = f"  {b.hex}" if b.hex else ""
        lines.append(f"{b.min_m:>12.0f}  {z:>8.2f}  {layer:>6d}  {b.name}{hexs}")
    return "\n".join(lines) + "\n"
