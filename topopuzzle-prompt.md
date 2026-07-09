# TopoPuzzle Studio — Build Prompt

You are an expert full-stack geospatial, CAD/mesh, and 3D-printing engineer. Build a personal web application + CLI that lets a user select any location on Earth and generate a 3D-printable topographic terrain model from real elevation data — optionally split into a multi-piece puzzle.

## Runtime target

This runs locally on a **Mac laptop (Apple Silicon)**. Native execution is the primary path — no Docker required to use the tool:

* Backend: Python 3.11+ in a venv (`uv` preferred), started with `uvicorn`. All geospatial/mesh deps (rasterio, pyproj, shapely, trimesh, manifold3d, scipy) must install from prebuilt arm64 wheels via pip — no Homebrew GDAL compilation step. If a dependency lacks arm64 wheels, pick an alternative.
* Frontend: Node 20+, `npm run dev` / `npm run build`.
* Provide a single `make dev` (or `just dev`) that starts both.
* Docker Compose remains as an optional convenience, not the primary setup path.

## Product boundary

Do not clone Terrain 6's branding, UI, trade dress, copy, exact puzzle aesthetics, or proprietary implementation. Build an original tool with similar broad functionality. All puzzle/connector geometry must be original and parametric.

## Target printer (primary design constraint)

The reference printer is a **Bambu Lab P2S with AMS** (0.4 mm nozzle, ~256 × 256 × 256 mm build volume, textured PEI plate).

Hard constraints derived from this:

* Assembled puzzle footprint and any single piece must be validated against a configurable build volume (default 250 × 250 mm usable).
* If a print-in-place layout is chosen, the entire assembled model must fit on one plate, and the app must warn when it doesn't and suggest per-piece printing instead.
* Export should include a **3MF** as a stretch goal: named objects per piece, millimeter units, transforms placing objects in printable positions. Bambu Studio plate/project metadata is best-effort and must be verified by importing into real Bambu Studio. STL-per-piece in a ZIP is the required baseline.
* Print settings guide should be written for Bambu Studio first, PrusaSlicer second.

## Core user flow

1. User opens a local/self-hosted web app (Docker Compose) or runs the CLI.
2. User searches for a place by name or enters lat/lon.
3. User selects a rectangular area on an interactive map (drag handles, live dimension readout in km and mm-at-scale).
4. User configures:
   * final physical size in mm (longest edge), auto-computing the other edge from the geographic aspect ratio
   * puzzle layout: none (solid model), 2×2, 2×3, 3×3, 4×4, or custom rows × columns
   * **assembly mode: `separate-pieces` (each piece a standalone STL) or `print-in-place` (pieces exported pre-assembled with printable clearance gaps so the puzzle prints as one plate and separates after printing)**
   * base thickness (default 3 mm)
   * vertical exaggeration (default 1.5–2×)
   * mesh resolution / max grid size
   * optional Gaussian smoothing
   * optional water flattening at a user-set elevation threshold
   * optional embossed underside labels ("A1", "B3", …)
   * optional tray/frame
   * export: STL per piece, combined STL, OBJ, 3MF (stretch)
5. App fetches or loads DEM data, generates a watertight terrain mesh, splits into pieces, previews in-browser (Three.js), and exports a ZIP with all models, README, attribution, settings manifest, and print notes.

## Assembly modes (this is a first-class feature, not an afterthought)

**separate-pieces (default):**
* Each piece is its own watertight STL with flat bottom, printed individually or arranged multiple-per-plate.
* Connector clearance default **0.20 mm per side** for FDM; user-configurable 0.05–0.5 mm.

**print-in-place:**
* All pieces exported in assembled positions as distinct objects (or one multi-body file), separated by a clearance gap.
* Gap default **0.4 mm** (≥ nozzle width) so walls don't fuse; expose as a parameter with a warning below 0.3 mm.
* Connectors in this mode must have no overhanging engagement that would fuse layer-to-layer — use straight-walled or slightly drafted tab/socket profiles, not undercuts.
* Validate that no two pieces are closer than the gap anywhere (mesh proximity check), and warn that print-in-place pieces will show the gap as a visible seam.
* Emit a note in the export README: run a small **calibration coupon** (one tab + one socket) before committing to a full print.
* Print-in-place mode may sacrifice connector complexity for reliable separation: prefer straight-sided tabs, simple key/slot geometry, or shallow dovetails only if printable without undercuts. The export must include a clearance coupon using the same connector geometry and gap settings, and the README must warn that print-in-place puzzles will have visible seams and may require flexing or deburring to separate.

## Architecture

* Frontend: Next.js + TypeScript + React; map via MapLibre GL with a **configurable raster/vector tile provider** (see Data providers); 3D preview via React Three Fiber.
* Backend: Python FastAPI.
* Geospatial: rasterio, pyproj, numpy, scipy, shapely.
* Mesh: trimesh + manifold3d. Prefer manifold3d for all CSG operations, but still validate every exported mesh independently with trimesh and explicit manifold/orientation checks — clean CSG does not guarantee valid output if inputs, transforms, or slicing logic are bad.
* Long-running generation: background task with polling/SSE progress; add RQ/Celery only if needed.
* Monorepo: `apps/web`, `apps/api`, `packages/mesh`, `packages/shared`, `examples`, `docs`, `tests`.
* License: **MIT**. Include a LICENSE file. Note in the README that generated models belong to the user. (The project may remain private; nothing in the design should assume public distribution.)

## Data providers

Clean provider interface:

```python
get_elevation_grid(bounds, target_resolution_m, crs) -> ElevationGrid
```

`ElevationGrid` must include: elevation array, CRS, resolution, nodata mask, provider name, upstream source names where available, attribution/license text, and data timestamp/version if available.

Priority order:
1. **Local GeoTIFF upload** — required MVP path, fully offline.
2. **AWS/Mapzen Terrain Tiles (terrarium PNG tiles)** — no API key, global coverage; online default. Must preserve the original upstream DEM source attribution from Tilezen/Mapzen documentation (SRTM, 3DEP, ETOPO1, etc.), not merely say "AWS Terrain Tiles."
3. **USGS 3DEP** — high-quality U.S. provider, later enhancement.
4. **OpenTopography** — optional API-key provider, later enhancement.
5. **OpenTopoData** — small-area / low-resolution preview / self-hosted fallback only. It is a point-lookup API; dense mesh grids would require excessive point sampling against the public instance, so cap request size unless self-hosted.

**Map tiles and elevation data are separate concerns.** The map UI must use a configurable tile provider; do not hard-code public OpenStreetMap tile servers as the production default (OSM's tile usage policy prohibits treating them as a free CDN). Attribution must be visible in the map UI and included in every export manifest. Network providers are optional and skipped in CI unless configured; export attribution may optionally be engraved on the tray underside.

## Geometry requirements (non-negotiable)

* Watertight, manifold, correctly-oriented normals; every exported mesh must pass `trimesh.is_watertight` and a validation report is included in the ZIP.
* Terrain top from resampled DEM grid; solid slab base; vertical side walls; flat bottom.
* Minimum feature guardrails: no wall or connector thinner than **1.2 mm** (3 × 0.4 mm perimeters) at the chosen physical scale — warn and auto-adjust or block export.
* Reproject bounds to the local UTM zone before meshing so mm dimensions are true.
* Fill small nodata gaps by interpolation; report gap percentage; warn above a threshold.
* Normalize so min terrain elevation sits at base top; apply exaggeration after normalization.
* **Overhang check:** compute max local terrain slope after exaggeration and warn when near-vertical or overhanging features (steep cliffs, deep embossed text, connector edges) are likely to print poorly. Do not claim support-free printing unless the overhang check passes.

## Puzzle splitting (MVP)

* Grid split with **parametric rounded tab/socket connectors**: radius/width, depth, clearance, min wall, alternating orientation, deterministic seed.
* Prioritize printability over jigsaw aesthetics; no thin necks, no undercuts in print-in-place mode.
* Flat bottoms on every piece; optional embossed underside label (0.6 mm deep, ≥ 8 pt equivalent stroke width).
* Connector pairing tests: every tab has exactly one mating socket; clearances applied symmetrically.

## Puzzle (later phases)

Organic seeded jigsaw curves, Voronoi pieces, magnet pockets (parametric diameter/depth, default 6 × 2 mm), multi-color contour banding via AMS material IDs in 3MF, engraved tray title/coordinates/scale bar/north arrow.

## Color & map features

STL is geometry-only; color arrives via the slicer or via 3MF material assignments. Support in this order:

**Tier 1 — elevation band color mapping (Phase 3, near-zero geometry work):**
* User picks N elevation bands (e.g., <1500 m green, 1500–2500 m tan, >2500 m white).
* App emits a `color-changes.txt` in the ZIP mapping each band boundary to the exact Z height in mm for the generated model, so the user sets AMS filament changes in Bambu Studio in seconds.
* Puzzle pieces in different colors need nothing: each piece is its own STL — just assign filaments per object in the slicer.

**Tier 2 — per-band contour meshes (Phase 5):**
* Optionally slice the solid into horizontal contour slabs, each a named object with an AMS material ID in the 3MF, so bands can sit at arbitrary elevations independent of layer heights.

**Tier 3 — OSM feature overlays (Phase 6):**
* New vector provider: Overpass API adapter fetching polylines/polygons for the selected bbox, filtered by feature class. Cache responses locally; offline GeoJSON upload as the network-free alternative.
* Default classes: major roads (`highway=motorway|trunk|primary|secondary`), hiking trails (`highway=path|footway` with `sac_scale` or inside park boundaries), waterways (`waterway=river|stream`), lakes (`natural=water`).
* Drape each polyline onto the terrain by sampling the DEM along it; buffer to a ribbon of configurable width.
* **Minimum feature width 1.0 mm at physical scale** (0.4 mm nozzle can't resolve less). Warn and auto-drop classes whose real-world width would render below this; show ground-distance-per-mm so the user understands the filtering.
* Three render modes per class: `deboss` (recessed groove, default 0.6 mm deep — single-color safe), `emboss` (raised 0.6 mm), `inlay` (flush ribbon as separate mesh object with its own 3MF material ID for AMS multi-color).
* Lakes/rivers combine with water flattening: flatten, recess 0.4 mm, optional separate material.
* Features must be clipped per puzzle piece and must not weaken connectors (no groove crossing a tab neck).
* OSM data requires ODbL attribution — add to the attribution manifest whenever overlays are used.

**Tier 4 — land-cover / satellite-derived surface coloring (Phase 7):**
* Goal: color the terrain's *top surface* by land cover — forest green, grassland/dry tan, bare rock gray, water blue — using discrete AMS filaments. FDM cannot print continuous imagery color; everything must quantize to 3–5 classes.
* **Primary data path: pre-classified land-cover rasters**, not raw imagery. New provider type alongside the DEM provider:
  ```python
  get_landcover_grid(bounds, target_resolution_m, crs) -> LandCoverGrid  # class array + legend + attribution
  ```
  1. **ESA WorldCover** (global 10 m, COGs on AWS open data, no key) — default.
  2. **NLCD** (U.S., higher class fidelity) — later.
  3. **Local classified raster upload** — offline path, same as GeoTIFF DEMs.
* **Alternative path (later): Sentinel-2 NDVI quantization** — classify vegetation vs dry/bare from the NIR band, not RGB green-ness (shadows and dark rock fool RGB). Treat as an optional adapter.
* User maps land-cover classes → up to N filament slots (default 4, matching one AMS); unmapped classes fall back to the base material.
* Geometry: classify DEM grid cells, resample the class raster to the mesh grid, then split only the **top ~0.8 mm shell** into per-class region meshes exported as named 3MF objects with material IDs. Body below the shell remains base material.
* **Purge-waste guardrails (critical):** apply majority filtering / morphological smoothing to the class raster; enforce a minimum region area (default 3 mm² at physical scale — merge or drop smaller); report estimated color-change count per layer and warn when it implies excessive purge waste or print time.
* Regions must be clipped per puzzle piece; class boundaries crossing connectors are fine (color only, no geometry change).
* Depends on 3MF multi-material export (Phase 5). A single-color fallback: render class boundaries as light debossed outlines instead.
* Land-cover sources carry their own licenses (WorldCover is CC BY 4.0) — include in the attribution manifest.

## Tray/frame (optional)

Rectangular tray slightly larger than the assembled puzzle, raised border, shallow recess matching footprint, optional engravings, must itself fit the build volume or export as split tray halves with alignment pins.

## Frontend UX

Left panel: search, coordinates, dimensions, layout, assembly mode, elevation scale, base/tray, advanced accordion. Main panel toggles map-select / 3D-preview. Progress states: fetching DEM → processing raster → generating terrain → splitting pieces → validating → packaging. Warnings for: area too large, triangle count too high, DEM gaps, huge STL estimate, connectors too small at scale, **model exceeds build plate**, **print-in-place gap below safe minimum**.

## CLI

```
topopuzzle generate \
  --bbox "-111.9,48.5,-111.7,48.7" \
  --rows 3 --cols 3 \
  --size-mm 180 \
  --z-exaggeration 1.8 \
  --base-mm 3 \
  --assembly print-in-place \
  --clearance-mm 0.4 \
  --provider terrain-tiles \
  --output ./out/glacier-puzzle.zip
```

Also: `topopuzzle calibrate --clearance-mm 0.2` emits a small tab/socket test coupon.

## Testing

Automated tests (no network required — use synthetic DEM fixtures: ramp, hill, flat, coastal-with-threshold, nodata patch):

* DEM crop/resample, normalization, exaggeration math
* watertightness of every exported mesh
* mm dimensions correct within tolerance
* piece count matches layout; connector pairing; no tab/socket overlap
* print-in-place proximity check (no gap violations)
* build-volume validation triggers correctly
* ZIP manifest contains attribution + full settings JSON
* generated STLs reload cleanly in trimesh

## Documentation

README (with screenshot/GIF placeholders), **macOS-native setup first** then optional Docker, provider notes, data attribution requirements, roadmap, troubleshooting, and a **print settings guide**: 0.4 mm nozzle, 0.16/0.20 mm layers, 3+ walls, 15–20 % infill, supports avoided by design where the overhang check passes (note exceptions for high exaggeration/cliffs), pieces flat on bottom, textured-plate first-layer notes, calibration coupon workflow, print-in-place vs separate-pieces tradeoffs.

## Implementation plan

* **Phase 1:** repo scaffold; local GeoTIFF → single watertight STL; CLI; tests with synthetic fixtures. *Acceptance: `topopuzzle generate --geotiff fixture.tif --size-mm 150` produces a valid STL that slices cleanly in Bambu Studio.*
* **Phase 2:** web map selection, 3D preview, backend job endpoint, ZIP export.
* **Phase 3:** grid puzzle split with parametric connectors, both assembly modes, calibration coupon, underside labels, tray, elevation-band `color-changes.txt` (Tier 1 color).
* **Phase 4:** terrain-tiles + OpenTopoData providers, attribution manifest, printability/build-volume warnings.
* **Phase 5:** 3MF (named objects, mm units, printable transforms; Bambu plate metadata best-effort, verified in real Bambu Studio), per-band contour meshes (Tier 2 color), magnet pockets, advanced puzzle styles.
* **Phase 6:** OSM feature overlays (Tier 3): Overpass adapter + GeoJSON upload, drape/buffer pipeline, deboss/emboss/inlay modes, per-piece clipping, connector-safety checks.
* **Phase 7:** land-cover surface coloring (Tier 4): WorldCover provider + local classified raster upload, class→filament mapping UI, top-shell region splitting, purge-waste guardrails; Sentinel-2 NDVI adapter optional.

## Working style

Produce working code, not just architecture. Small well-tested functions, deterministic seeds, small logical commits, example outputs from synthetic DEMs committed under `examples/`. Start with the repo scaffold, then the geometry core and CLI, before any web UI.