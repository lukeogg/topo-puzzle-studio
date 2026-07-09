# Print settings guide

Written for **Bambu Studio** first, **PrusaSlicer** second. Reference printer:
Bambu Lab P2S with AMS, 0.4 mm nozzle, textured PEI plate, ~256 mm cube (use a
conservative 250 × 250 mm usable footprint).

## Slicer settings

| setting | value |
|---------|-------|
| Nozzle | 0.4 mm |
| Layer height | 0.16 mm (fine) or 0.20 mm (fast) |
| Wall loops / perimeters | 3+ (this backs the 1.2 mm minimum feature guardrail) |
| Infill | 15–20% (gyroid or grid) |
| Supports | **off by design** where the overhang check passes — see below |
| First layer | textured-plate profile; clean plate, slight z-offset tuning if needed |

Pieces are generated with a **flat bottom**, so they sit directly on the plate — no
brim usually needed for the small footprints; add a brim for tall, narrow pieces.

## Supports and overhangs

The generator runs an **overhang check** (max local terrain slope after
exaggeration) and records it in `validation-report.json`. When it passes (slope
comfortably below vertical), the model prints support-free.

Enable supports when:
- you used **high vertical exaggeration** and the report warns about steep slopes,
- the terrain has genuine **cliffs / canyons**, or
- you added deep embossed features on steep faces.

Do not assume support-free printing if the overhang check warns.

## Assembly modes

### Separate pieces (default)
Each piece is its own STL. Print individually or several per plate. Assign a
filament per object in the slicer for per-piece colour. Connectors interlock with a
per-side clearance (default 0.20 mm). If pieces are too tight or too loose, adjust
`--clearance-mm` and regenerate. **Print `coupon.stl` first** to dial in the fit.

### Print-in-place
The whole puzzle prints as one plate with a seam gap (default 0.4 mm ≥ nozzle
width) so pieces separate afterward. Notes:
- Seams are **visible** and pieces may need gentle **flexing / deburring** to free.
- Connectors are **straight-walled (no undercuts)** so layers don't fuse.
- Keep the gap **≥ 0.3 mm**; the app warns below that. Below the gap the walls fuse.
- The assembled model must **fit one plate** — the app errors and suggests
  separate-pieces if it doesn't.
- **Always print `coupon.stl` first** to confirm the gap frees cleanly.

## Calibration coupon workflow

1. `topopuzzle calibrate --clearance-mm 0.20 -o coupon.stl` (or use the `coupon.stl`
   in any export — it uses that run's exact connector geometry and clearance/gap).
2. Print it. For separate-pieces, the tab should insert with light friction. For
   print-in-place, the two halves should separate without tools but not rattle.
3. Too tight → increase clearance/gap by 0.05 mm. Too loose → decrease. Regenerate.

## AMS / colour

STL is geometry only. For elevation-band colour, open `color-changes.txt` — it lists
the exact **Z height (mm)** where each band begins. In Bambu Studio, add a filament
change at each height (right-click the layer at that Z). For puzzle colour, just
assign a filament per piece object (each piece is its own STL / a named object in the
3MF).

## PrusaSlicer notes

Same geometry applies. Use "Color Change" at the Z heights from `color-changes.txt`.
Multi-material colour via the 3MF named objects is best-effort; verify in-slicer.
