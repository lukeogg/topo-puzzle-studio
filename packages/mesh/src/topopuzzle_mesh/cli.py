"""``topopuzzle`` command-line interface."""

from __future__ import annotations

import os
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import AssemblyMode, Bounds, ConnectorStyle, GenerateSettings
from .export import calibration_coupon, mesh_to_stl_bytes, package_zip
from .pipeline import generate as run_generate

app = typer.Typer(add_completion=False, help="Generate 3D-printable topographic terrain puzzles.")
console = Console()


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
    formats: str = typer.Option("stl,3mf", help="Comma list: stl,3mf,obj."),
):
    """Generate a terrain puzzle ZIP."""
    if provider == "geotiff" and not geotiff:
        raise typer.BadParameter("geotiff provider requires --geotiff")

    connector_style = (
        ConnectorStyle.STRAIGHT_TAB
        if assembly == "print-in-place"
        else ConnectorStyle.ROUNDED_TAB
    )
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
        formats=[f.strip() for f in formats.split(",") if f.strip()],
    )
    settings.connector.style = connector_style
    settings.connector.clearance_mm = clearance_mm

    with console.status("[bold green]Generating…") as status:
        def prog(stage: str, frac: float):
            status.update(f"[bold green]{stage}[/] {frac*100:.0f}%")

        out = run_generate(settings, progress=prog)
        status.update("[bold green]packaging…")
        package_zip(out.result, out.report, output)

    _print_report(out, output)


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


def _print_report(out, output: str) -> None:
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
    size = os.path.getsize(output) / 1e6
    if out.report.has_errors:
        console.print(f"[red]⚠ validation errors present[/] — see report. Wrote {output} ({size:.1f} MB)")
    else:
        console.print(f"[bold green]✓ wrote[/] {output} ({size:.1f} MB)")


if __name__ == "__main__":
    app()
