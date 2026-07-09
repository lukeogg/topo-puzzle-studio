"""Mesh writers (STL / OBJ / 3MF), the calibration coupon, and the ZIP packager.

The ZIP is the deliverable: per-piece STLs (the required baseline), an optional
combined STL / OBJ / 3MF, plus the manifest, attribution, color-changes,
validation report, print notes, README, and a calibration coupon.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass

import trimesh
from shapely.geometry import box

from . import connectors
from .color import color_changes_text
from .config import AssemblyMode, ConnectorStyle, GenerateSettings
from .labels import emboss_label
from .puzzle import PuzzleResult
from .validate import ValidationReport


# --------------------------------------------------------------------------- #
# Positioning helpers
# --------------------------------------------------------------------------- #


def _to_origin(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    m = mesh.copy()
    b = m.bounds
    m.apply_translation((-b[0][0], -b[0][1], -b[0][2]))
    return m


def finalize_pieces(result: PuzzleResult) -> list[tuple[str, trimesh.Trimesh]]:
    """Return (label, assembled-mesh) with underside labels applied if enabled."""
    out = []
    for p in result.pieces:
        mesh = p.mesh
        if result.settings.labels and not result.settings.is_solid:
            try:
                mesh = emboss_label(
                    mesh, p.label, depth_mm=result.settings.label_depth_mm,
                    height_mm=max(6.0, min(p.mesh.extents[0], p.mesh.extents[1]) * 0.25),
                )
            except Exception:  # labelling is best-effort; never fail the export
                mesh = p.mesh
        out.append((p.label, mesh))
    return out


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #


def mesh_to_stl_bytes(mesh: trimesh.Trimesh) -> bytes:
    return mesh.export(file_type="stl")


def mesh_to_obj_bytes(mesh: trimesh.Trimesh) -> bytes:
    data = mesh.export(file_type="obj")
    return data.encode() if isinstance(data, str) else data


def scene_to_3mf_bytes(named: list[tuple[str, trimesh.Trimesh]]) -> bytes:
    """Named objects in one 3MF, millimetre units, at their given transforms."""
    scene = trimesh.Scene()
    for name, mesh in named:
        scene.add_geometry(mesh, node_name=name, geom_name=name)
    data = scene.export(file_type="3mf")
    return data if isinstance(data, bytes) else bytes(data)


# --------------------------------------------------------------------------- #
# Calibration coupon
# --------------------------------------------------------------------------- #


def calibration_coupon(settings: GenerateSettings) -> trimesh.Trimesh:
    """A small tab + socket pair using the run's connector geometry and fit.

    Printing this first verifies the chosen clearance/gap before committing to a
    full puzzle.  Two 24 mm blocks: one carries the tab, the other the socket.
    """
    style = settings.connector.style
    if style is ConnectorStyle.NONE:
        style = ConnectorStyle.STRAIGHT_TAB
    conn = settings.connector.model_copy(update={"style": style, "depth_mm": min(settings.connector.depth_mm, 6.0)})
    size, h = 24.0, max(4.0, settings.base_mm + 2.0)
    edge = size

    tab = connectors.tab_polygon(
        conn, edge_length=edge, seam_is_vertical=True,
        center=(size, size / 2), into_positive=True,
    )
    if settings.assembly is AssemblyMode.PRINT_IN_PLACE:
        off = settings.gap_mm / 2.0
    else:
        off = settings.connector.clearance_mm / 2.0

    block_a = box(0, 0, size, size).union(tab).buffer(-off, join_style=2)
    block_b = box(size + 4, 0, 2 * size + 4, size)
    socket = connectors.tab_polygon(
        conn, edge_length=edge, seam_is_vertical=True,
        center=(size + 4, size / 2), into_positive=False,
    )
    block_b = block_b.difference(socket).buffer(-off, join_style=2)

    parts = []
    for poly in (block_a, block_b):
        geom = poly.geoms[0] if poly.geom_type == "MultiPolygon" else poly
        parts.append(trimesh.creation.extrude_polygon(geom, height=h))
    coupon = trimesh.util.concatenate(parts)
    return coupon


# --------------------------------------------------------------------------- #
# Manifest / notes
# --------------------------------------------------------------------------- #


@dataclass
class ExportInfo:
    settings: GenerateSettings
    report: ValidationReport
    result: PuzzleResult


def attribution_text(result: PuzzleResult) -> str:
    a = result.terrain.grid.attribution
    lines = [
        "TopoPuzzle Studio — data attribution",
        "=" * 40,
        f"Elevation provider : {a.provider}",
        f"Upstream source(s) : {', '.join(a.sources) or 'unknown'}",
        f"License            : {a.license or 'see provider'}",
    ]
    if a.timestamp:
        lines.append(f"Data timestamp     : {a.timestamp}")
    if a.text:
        lines += ["", a.text]
    lines += [
        "",
        "Generated models belong to you (see LICENSE, MIT).",
        "Verify any required attribution before public redistribution of the source data.",
    ]
    return "\n".join(lines) + "\n"


def print_notes_text(result: PuzzleResult) -> str:
    s = result.settings
    pip = s.assembly is AssemblyMode.PRINT_IN_PLACE
    W, H = result.assembled_footprint_mm
    lines = [
        "# Print notes",
        "",
        "Tuned for a Bambu Lab P2S (0.4 mm nozzle, textured PEI plate); PrusaSlicer works too.",
        "",
        "## Recommended settings",
        "- Nozzle 0.4 mm, layer height 0.16–0.20 mm",
        "- 3+ wall loops (perimeters), 15–20% infill",
        "- No supports where the overhang check passes; enable supports for high",
        "  exaggeration or genuine cliffs (see validation-report.json → overhang).",
        "- Pieces sit flat on their printed bottom; first-layer notes for textured plates apply.",
        "",
        f"## This model — {s.assembly.value}",
        f"- Assembled footprint: {W:.1f} × {H:.1f} mm",
        f"- Pieces: {len(result.pieces)} ({s.rows}×{s.cols}), base {s.base_mm} mm, {s.z_exaggeration}× exaggeration",
    ]
    if pip:
        lines += [
            f"- Print-in-place seam gap: {s.gap_mm} mm — prints as one plate and separates after printing.",
            "- Seams are VISIBLE and pieces may need gentle flexing/deburring to free them.",
            "- Connectors are straight-walled (no undercuts) so layers don't fuse.",
            "- **Print coupon.stl first** to confirm the gap frees cleanly before the full plate.",
        ]
    else:
        lines += [
            f"- Separate pieces, connector clearance {s.connector.clearance_mm} mm per side.",
            "- Print pieces individually or several per plate; assign a filament per piece for colour.",
            "- **Print coupon.stl first** to confirm the tab/socket fit at your clearance.",
        ]
    lines += ["", "## Calibration coupon", "coupon.stl reproduces one tab + one socket at the exact",
              "connector geometry and clearance/gap above. Adjust clearance and regenerate if the fit is off.", ""]
    return "\n".join(lines)


def readme_text(result: PuzzleResult) -> str:
    s = result.settings
    return (
        f"# TopoPuzzle Studio export\n\n"
        f"Place: {s.place_name or 'custom bounds'}\n"
        f"Layout: {s.rows}×{s.cols} · {s.assembly.value} · longest edge {s.size_mm} mm\n\n"
        "## Contents\n"
        "- `*.stl` — one watertight STL per piece (labels A1…)\n"
        "- `combined.stl` / `model.3mf` / `model.obj` — assembled reference (if selected)\n"
        "- `coupon.stl` — connector calibration coupon (print this first)\n"
        "- `color-changes.txt` — AMS filament-change Z heights per elevation band\n"
        "- `settings.json` — the exact settings used (reproducible)\n"
        "- `validation-report.json` — watertight / build-volume / overhang checks\n"
        "- `attribution.txt` — elevation data source and license\n"
        "- `print-notes.md` — slicer + printing guidance\n\n"
        "Generated models belong to you (MIT).\n"
    )


# --------------------------------------------------------------------------- #
# ZIP packager
# --------------------------------------------------------------------------- #


def package_zip(result: PuzzleResult, report: ValidationReport, out_path: str) -> str:
    """Write the full deliverable ZIP to ``out_path`` and return the path."""
    s = result.settings
    named = finalize_pieces(result)  # assembled coords, labels applied

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # Per-piece STL (each at its own origin) — the required baseline.
        for label, mesh in named:
            z.writestr(f"{label}.stl", mesh_to_stl_bytes(_to_origin(mesh)))

        if "stl" in s.formats and len(named) > 1:
            combined = trimesh.util.concatenate([m for _, m in named])
            z.writestr("combined.stl", mesh_to_stl_bytes(combined))
        if "3mf" in s.formats:
            z.writestr("model.3mf", scene_to_3mf_bytes(named))
        if "obj" in s.formats:
            combined = trimesh.util.concatenate([m for _, m in named])
            z.writestr("model.obj", mesh_to_obj_bytes(combined))

        z.writestr("coupon.stl", mesh_to_stl_bytes(calibration_coupon(s)))
        z.writestr("color-changes.txt", color_changes_text(result.terrain, s))
        z.writestr("attribution.txt", attribution_text(result))
        z.writestr("print-notes.md", print_notes_text(result))
        z.writestr("README.md", readme_text(result))
        z.writestr("validation-report.json", json.dumps(report.as_dict(), indent=2))
        settings_json = json.loads(s.model_dump_json())
        settings_json["_footprint_mm"] = list(result.assembled_footprint_mm)
        settings_json["_piece_count"] = len(result.pieces)
        z.writestr("settings.json", json.dumps(settings_json, indent=2))

    with open(out_path, "wb") as f:
        f.write(buf.getvalue())
    return out_path
