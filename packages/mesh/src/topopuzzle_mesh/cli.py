"""``topopuzzle`` command-line interface."""

from __future__ import annotations

import os
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import (
    AssemblyMode,
    Bounds,
    ConnectorStyle,
    ElevationBand,
    GenerateSettings,
    LandCoverClass,
    LandCoverSettings,
    MagnetSettings,
    OverlayClass,
    OverlaySettings,
    RenderMode,
    TraySettings,
)
from .export import calibration_coupon, mesh_to_stl_bytes, package_zip
from .pipeline import generate as run_generate

app = typer.Typer(add_completion=False, help="Generate 3D-printable topographic terrain puzzles.")
console = Console()


def _parse_bands(items: Optional[List[str]]) -> list[ElevationBand]:
    bands = []
    for it in items or []:
        parts = it.split(":")
        if len(parts) < 2:
            raise typer.BadParameter(f"--band must be 'min_m:name[:hex]', got {it!r}")
        bands.append(ElevationBand(min_m=float(parts[0]), name=parts[1], hex=parts[2] if len(parts) > 2 else None))
    return bands


def _parse_landcover_map(spec: Optional[str]) -> list[LandCoverClass]:
    out = []
    for tok in (spec or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        parts = tok.split(":")
        out.append(LandCoverClass(code=int(parts[0]), name=parts[1] if len(parts) > 1 else "", hex=parts[2] if len(parts) > 2 else None))
    return out


def _parse_overlay_classes(spec: Optional[str]) -> list[OverlayClass]:
    return [OverlayClass(c.strip()) for c in (spec or "").split(",") if c.strip()]


@app.command()
def generate(
    output: str = typer.Option(..., "--output", "-o", help="Output ZIP path."),
    bbox: Optional[str] = typer.Option(None, help="west,south,east,north (lon/lat)."),
    geotiff: Optional[str] = typer.Option(None, help="Local GeoTIFF DEM path."),
    provider: str = typer.Option("geotiff", help="Elevation provider."),
    rows: int = typer.Option(1, help="Puzzle rows."),
    cols: int = typer.Option(1, help="Puzzle columns."),
    size_mm: float = typer.Option(180.0, "--size-mm", help="Longest edge in mm."),
    z_exaggeration: float = typer.Option(1.8, "--z-exaggeration", help="Vertical exaggeration."),
    base_mm: float = typer.Option(3.0, "--base-mm", help="Base thickness in mm."),
    assembly: str = typer.Option("separate-pieces", help="separate-pieces | print-in-place."),
    clearance_mm: float = typer.Option(0.20, "--clearance-mm", help="Separate-pieces per-side clearance."),
    gap_mm: float = typer.Option(0.4, "--gap-mm", help="Print-in-place seam gap."),
    max_grid: int = typer.Option(400, "--max-grid", help="Max mesh grid cells on the long side."),
    smoothing: float = typer.Option(0.0, help="Gaussian smoothing sigma (0 = off)."),
    labels: bool = typer.Option(False, help="Emboss underside piece labels."),
    connector: Optional[str] = typer.Option(None, help="Connector style: rounded-tab|straight-tab|organic-tab|voronoi-tab|none."),
    # --- magnets ---
    magnets: bool = typer.Option(False, help="Add magnet pockets to each piece bottom."),
    magnet_diameter_mm: float = typer.Option(6.0, "--magnet-diameter-mm", help="Magnet pocket diameter."),
    magnet_depth_mm: float = typer.Option(2.0, "--magnet-depth-mm", help="Magnet pocket depth."),
    # --- tray ---
    tray: bool = typer.Option(False, help="Include a display tray/frame."),
    tray_split: bool = typer.Option(True, "--tray-split/--no-tray-split", help="Split an oversized tray into pinned halves."),
    # --- Tier-2 colour ---
    contour_bands: bool = typer.Option(False, "--contour-bands", help="Emit per-band contour 3MF (needs --band)."),
    band: Optional[List[str]] = typer.Option(None, "--band", help="Elevation band 'min_m:name[:hex]' (repeatable)."),
    # --- Tier-3 overlays ---
    overlays: bool = typer.Option(False, help="Drape OSM feature overlays."),
    overlay_classes: str = typer.Option("roads,waterways,lakes", "--overlay-classes", help="Comma list: roads,trails,waterways,lakes."),
    overlay_render: str = typer.Option("deboss", "--overlay-render", help="deboss|emboss|inlay."),
    overlay_geojson: Optional[str] = typer.Option(None, "--overlay-geojson", help="Local GeoJSON of features (offline; else Overpass)."),
    overlay_width_scale: float = typer.Option(1.0, "--overlay-width-scale", help="Scale per-class ribbon widths."),
    # --- Tier-4 land cover ---
    landcover: bool = typer.Option(False, help="Colour the top shell by land cover."),
    landcover_raster: Optional[str] = typer.Option(None, "--landcover-raster", help="Local classified raster (offline; else ESA WorldCover)."),
    landcover_map: Optional[str] = typer.Option(None, "--landcover-map", help="Class map 'code:name:hex,…' (else auto top-N)."),
    landcover_shell_mm: float = typer.Option(0.8, "--landcover-shell-mm", help="Coloured top-shell thickness."),
    formats: str = typer.Option("stl,3mf", help="Comma list: stl,combined-stl,obj,3mf."),
    force: bool = typer.Option(False, "--force", help="Write the ZIP even if hard validation errors are present."),
):
    """Generate a terrain puzzle ZIP."""
    if provider == "geotiff" and not geotiff:
        raise typer.BadParameter("geotiff provider requires --geotiff")

    if connector:
        connector_style = ConnectorStyle(connector)
    else:
        connector_style = (
            ConnectorStyle.STRAIGHT_TAB if assembly == "print-in-place" else ConnectorStyle.ROUNDED_TAB
        )
    bands = _parse_bands(band)
    settings = GenerateSettings(
        bounds=Bounds.from_csv(bbox) if bbox else None,
        provider=provider,
        geotiff_path=geotiff,
        rows=rows,
        cols=cols,
        size_mm=size_mm,
        z_exaggeration=z_exaggeration,
        base_mm=base_mm,
        assembly=AssemblyMode(assembly),
        gap_mm=gap_mm,
        max_grid=max_grid,
        smoothing_sigma=smoothing,
        labels=labels,
        bands=bands,
        contour_bands=contour_bands,
        magnets=MagnetSettings(enabled=magnets, diameter_mm=magnet_diameter_mm, depth_mm=magnet_depth_mm),
        tray=TraySettings(enabled=tray, split_oversize=tray_split),
        overlays=OverlaySettings(
            enabled=overlays,
            classes=_parse_overlay_classes(overlay_classes),
            render=RenderMode(overlay_render),
            width_scale=overlay_width_scale,
            geojson_path=overlay_geojson,
        ),
        landcover=LandCoverSettings(
            enabled=landcover,
            raster_path=landcover_raster,
            mapping=_parse_landcover_map(landcover_map),
            shell_mm=landcover_shell_mm,
        ),
        formats=[f.strip() for f in formats.split(",") if f.strip()],
    )
    settings.connector.style = connector_style
    settings.connector.clearance_mm = clearance_mm

    with console.status("[bold green]Generating…") as status:
        def prog(stage: str, frac: float):
            status.update(f"[bold green]{stage}[/] {frac*100:.0f}%")

        out = run_generate(settings, progress=prog)
        # Hard validation errors block export by default (spec: block, don't ship
        # an unprintable model) unless the user passes --force.
        wrote = False
        if not out.report.has_errors or force:
            status.update("[bold green]packaging…")
            package_zip(out.result, out.report, output)
            wrote = True

    _print_report(out, output if wrote else None, forced=force)
    if out.report.has_errors and not force:
        console.print(
            "[red]✗ export blocked — hard validation errors above.[/] "
            "Fix the settings and regenerate, or pass [bold]--force[/] to write anyway."
        )
        raise typer.Exit(1)


@app.command()
def calibrate(
    output: str = typer.Option("coupon.stl", "--output", "-o", help="Coupon STL path."),
    clearance_mm: float = typer.Option(0.20, "--clearance-mm", help="Per-side clearance."),
    assembly: str = typer.Option("separate-pieces", help="separate-pieces | print-in-place."),
    gap_mm: float = typer.Option(0.4, "--gap-mm", help="Print-in-place seam gap."),
):
    """Emit a small tab/socket calibration coupon."""
    s = GenerateSettings(assembly=AssemblyMode(assembly), gap_mm=gap_mm)
    s.connector.clearance_mm = clearance_mm
    if assembly == "print-in-place":
        s.connector.style = ConnectorStyle.STRAIGHT_TAB
    coupon = calibration_coupon(s)
    with open(output, "wb") as f:
        f.write(mesh_to_stl_bytes(coupon))
    console.print(f"[green]wrote coupon[/] → {output}  (watertight={coupon.is_watertight})")


def _print_report(out, output: str | None, forced: bool = False) -> None:
    r = out.result
    W, H = r.assembled_footprint_mm
    table = Table(title="TopoPuzzle generation")
    table.add_column("check")
    table.add_column("result")
    table.add_row("pieces", str(len(r.pieces)))
    table.add_row("assembled mm", f"{W:.1f} × {H:.1f}")
    table.add_row("assembly", r.settings.assembly.value)
    for c in out.report.checks:
        mark = "[green]✓[/]" if c.ok else ("[red]✗[/]" if c.level == "error" else "[yellow]![/]")
        table.add_row(f"{mark} {c.name}", c.message)
    console.print(table)
    if output is None:
        return  # export was blocked; the caller prints the reason
    size = os.path.getsize(output) / 1e6
    if out.report.has_errors and forced:
        console.print(f"[yellow]⚠ forced write despite validation errors[/] — {output} ({size:.1f} MB)")
    else:
        console.print(f"[bold green]✓ wrote[/] {output} ({size:.1f} MB)")


if __name__ == "__main__":
    app()
