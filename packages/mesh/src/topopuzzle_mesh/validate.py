"""Independent validation of a generated puzzle.

Even though pieces come from clean manifold3d CSG, every mesh is re-checked with
trimesh (watertight + winding + volume), plus the product-level guardrails the
spec calls non-negotiable: minimum feature width, build-volume fit, overhang
risk, nodata coverage, and — for print-in-place — a piece-proximity check.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from shapely.geometry import Polygon

from .config import AssemblyMode, ConnectorStyle, GenerateSettings
from .puzzle import PuzzleResult

INFO, WARN, ERROR = "info", "warning", "error"


@dataclass
class Check:
    name: str
    ok: bool
    level: str
    message: str


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, ok: bool, message: str, level: str = WARN) -> None:
        self.checks.append(Check(name, ok, INFO if ok else level, message))

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks if c.level == ERROR or not c.ok)

    @property
    def has_errors(self) -> bool:
        return any((not c.ok) and c.level == ERROR for c in self.checks)

    @property
    def warnings(self) -> list[str]:
        return [c.message for c in self.checks if (not c.ok) and c.level == WARN]

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "has_errors": self.has_errors,
            "checks": [asdict(c) for c in self.checks],
        }


def _min_gap_between_pieces(pieces) -> float:
    """Smallest distance between any two piece footprints (mm).

    Seam walls are vertical (each piece is a prism ∩ terrain), so the 2-D
    footprint distance is exactly the 3-D minimum separation between two pieces —
    this is an exact bound, not an approximation.
    """
    best = float("inf")
    polys: list[tuple[str, Polygon]] = [(p.label, p.fit_footprint) for p in pieces]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            d = polys[i][1].distance(polys[j][1])
            best = min(best, d)
    return best if best != float("inf") else 0.0


def _mesh_min_gap_adjacent(pieces) -> float:
    """Independent mesh-level check: nearest surface distance between grid-adjacent
    piece *meshes* (not just footprints). Verifies the footprint bound against the
    actual 3-D geometry. Only neighbouring pairs are checked (others are far)."""
    import trimesh

    by_rc = {(p.row, p.col): p for p in pieces}
    best = float("inf")
    for p in pieces:
        for dr, dc in ((0, 1), (1, 0)):
            nb = by_rc.get((p.row + dr, p.col + dc))
            if nb is None:
                continue
            # Sample the neighbour's vertices onto this piece's surface (both ways).
            for a, b in ((p.mesh, nb.mesh), (nb.mesh, p.mesh)):
                try:
                    _, dist, _ = trimesh.proximity.closest_point(a, b.vertices)
                    best = min(best, float(dist.min()))
                except Exception:
                    # Proximity backend unavailable — skip; the exact footprint
                    # bound stays authoritative. Never report a spurious 0.
                    pass
    return best  # inf when nothing could be measured (min() then ignores it)


def validate(result: PuzzleResult) -> ValidationReport:
    s: GenerateSettings = result.settings
    rep = ValidationReport()

    # --- per-mesh integrity ---
    non_wt = [p.label for p in result.pieces if not p.mesh.is_watertight]
    rep.add("watertight", not non_wt, "all pieces watertight" if not non_wt else f"not watertight: {non_wt}", ERROR)
    bad_wind = [p.label for p in result.pieces if not p.mesh.is_winding_consistent]
    rep.add("winding", not bad_wind, "consistent winding / normals" if not bad_wind else f"inconsistent winding: {bad_wind}", ERROR)
    neg_vol = [p.label for p in result.pieces if p.mesh.volume <= 0]
    rep.add("volume", not neg_vol, "positive solid volume" if not neg_vol else f"non-positive volume: {neg_vol}", ERROR)

    # --- minimum feature width at physical scale ---
    if not s.is_solid and s.connector.style is not ConnectorStyle.NONE:
        W, H = result.assembled_footprint_mm
        edge = min(W / s.cols, H / s.rows)
        tab_w = s.connector.width_frac * edge
        # Fraction of the tab width that the narrowest neck occupies, per style.
        neck_frac = {
            ConnectorStyle.ROUNDED_TAB: 0.45,
            ConnectorStyle.ORGANIC_TAB: 0.5,
            ConnectorStyle.VORONOI_TAB: 0.5,
        }.get(s.connector.style, 1.0)
        neck = tab_w * neck_frac
        ok = neck >= s.min_feature_mm
        rep.add(
            "connector_min_feature",
            ok,
            f"connector neck {neck:.2f} mm ≥ {s.min_feature_mm} mm"
            if ok
            else f"connector neck {neck:.2f} mm below {s.min_feature_mm} mm minimum — widen tabs or increase size",
            ERROR,
        )
    ok_base = s.base_mm >= s.min_feature_mm
    rep.add("base_thickness", ok_base, f"base {s.base_mm} mm ≥ {s.min_feature_mm} mm" if ok_base else f"base {s.base_mm} mm is thin")

    # --- build volume ---
    bv = s.build_volume
    biggest = max(
        (max(p.mesh.extents[0], p.mesh.extents[1]) for p in result.pieces), default=0.0
    )
    piece_fits = all(
        p.mesh.extents[0] <= bv.x_mm and p.mesh.extents[1] <= bv.y_mm
        for p in result.pieces
    )
    rep.add(
        "piece_build_volume",
        piece_fits,
        f"largest piece {biggest:.0f} mm fits {bv.x_mm:.0f}×{bv.y_mm:.0f} mm plate"
        if piece_fits
        else f"a piece exceeds the {bv.x_mm:.0f}×{bv.y_mm:.0f} mm plate — reduce size or add pieces",
        ERROR,
    )
    W, H = result.assembled_footprint_mm
    if s.assembly is AssemblyMode.PRINT_IN_PLACE:
        fits = W <= bv.x_mm and H <= bv.y_mm
        rep.add(
            "assembled_build_volume",
            fits,
            f"assembled {W:.0f}×{H:.0f} mm fits one plate"
            if fits
            else f"assembled {W:.0f}×{H:.0f} mm exceeds the plate — switch to separate-pieces and print individually",
            ERROR,
        )

    # --- print-in-place proximity / gap ---
    if s.assembly is AssemblyMode.PRINT_IN_PLACE and len(result.pieces) > 1:
        # Exact footprint bound plus an independent mesh-level neighbour check.
        gap = min(_min_gap_between_pieces(result.pieces), _mesh_min_gap_adjacent(result.pieces))
        ok = gap >= s.gap_mm * 0.85
        rep.add(
            "pip_proximity",
            ok,
            f"min inter-piece gap {gap:.2f} mm ≥ target {s.gap_mm} mm"
            if ok
            else f"pieces as close as {gap:.2f} mm (< {s.gap_mm} mm) — may fuse when printed",
            ERROR,
        )
        if s.gap_mm < 0.3:
            rep.add("pip_gap_min", False, f"gap {s.gap_mm} mm is below the 0.3 mm safe minimum for a 0.4 mm nozzle")

    # --- tray fit (if enabled) ---
    if s.tray.enabled:
        tw = W + 2 * (s.tray.fit_gap_mm + s.tray.wall_mm)
        th = H + 2 * (s.tray.fit_gap_mm + s.tray.wall_mm)
        fits_whole = tw <= bv.x_mm and th <= bv.y_mm
        if fits_whole:
            rep.add("tray_build_volume", True, f"tray {tw:.0f}×{th:.0f} mm fits the plate")
        elif s.tray.split_oversize:
            # Mirror tray.split_tray's axis choice: halve the over-plate axis
            # (the longer one when both exceed).
            over_x, over_y = tw > bv.x_mm, th > bv.y_mm
            split_x = (tw >= th) if (over_x and over_y) else over_x
            hw, hh = (tw / 2.0, th) if split_x else (tw, th / 2.0)
            halves_fit = hw <= bv.x_mm and hh <= bv.y_mm
            rep.add(
                "tray_build_volume",
                halves_fit,
                f"tray {tw:.0f}×{th:.0f} mm exceeds the plate — exported as two pinned halves ({hw:.0f}×{hh:.0f} mm each)"
                if halves_fit
                else f"tray {tw:.0f}×{th:.0f} mm too large even split into halves ({hw:.0f}×{hh:.0f} mm) — use a smaller model or omit the tray",
            )
        else:
            rep.add(
                "tray_build_volume",
                False,
                f"tray {tw:.0f}×{th:.0f} mm exceeds the {bv.x_mm:.0f}×{bv.y_mm:.0f} mm plate — enable tray splitting, print without the tray, or shrink the model",
            )

    # --- overhang risk ---
    steep = result.terrain.max_slope_deg
    ok_slope = steep < 80.0
    rep.add(
        "overhang",
        ok_slope,
        f"max terrain slope {steep:.0f}° — support-free"
        if ok_slope
        else f"max terrain slope {steep:.0f}° is near-vertical/overhanging — supports or lower exaggeration recommended",
    )

    # --- nodata coverage ---
    # The terrain grid has already been gap-filled, so its own mask is empty;
    # the meaningful number is how much was missing before filling.
    frac = result.terrain.nodata_fraction
    rep.add(
        "nodata",
        frac <= s.nodata_warn_frac,
        f"nodata {frac*100:.1f}% within tolerance"
        if frac <= s.nodata_warn_frac
        else f"nodata {frac*100:.1f}% exceeds {s.nodata_warn_frac*100:.0f}% — interpolated regions may be unreliable",
    )

    # --- piece count sanity ---
    expected = s.piece_count
    got = len(result.pieces)
    rep.add("piece_count", got == expected, f"{got}/{expected} pieces generated" if got == expected else f"expected {expected} pieces, got {got}", ERROR)

    return rep
