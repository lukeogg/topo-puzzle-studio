# Roadmap

Status of the phased plan. ✅ done · 🟡 partial · ⬜ planned.

- **Phase 1 — geometry core + CLI + tests** ✅
  Local GeoTIFF → watertight STL; CLI (`generate`, `calibrate`); synthetic-fixture
  test suite. *Acceptance: `topopuzzle generate --geotiff fixture.tif --size-mm 150`
  produces a valid STL — met and tested.*
- **Phase 2 — web + backend** ✅
  MapLibre area selection, React Three Fiber preview, FastAPI job endpoint with SSE
  progress and GLB preview, ZIP export.
- **Phase 3 — puzzles + color Tier 1** ✅
  Grid split with parametric rounded/straight tab-socket connectors, both assembly
  modes, calibration coupon, embossed underside labels, optional tray/frame,
  elevation-band `color-changes.txt`.
- **Phase 4 — providers + warnings** ✅
  Terrain-tiles provider ✅ and attribution manifest ✅; printability/build-volume
  warnings ✅. OpenTopoData ✅, USGS 3DEP ✅, OpenTopography (API-key) ✅. Richer
  geocoding ✅ (Nominatim→Photon fallback, structured results, in-memory cache).
- **Phase 5 — 3MF + color Tier 2** ✅
  3MF named objects in mm at printable transforms ✅ (Bambu plate metadata
  best-effort, verify in Bambu Studio). Per-band contour meshes ✅ (Tier-2 colour:
  `model-banded.3mf`, CSG-exact slab partition). Magnet pockets ✅ (parametric
  blind pockets in each piece bottom). Advanced puzzle styles ✅ (seeded
  organic-tab + faceted voronoi-tab connectors behind the same seam API).
  Tray split-halves with alignment pins when oversized ✅.
- **Phase 6 — OSM overlays (Tier 3)** ✅
  Overpass adapter + GeoJSON upload ✅; drape/buffer to model-space ribbons with
  min-width filtering ✅; deboss/emboss baked into the heightfield + inlay flush
  ribbons via top-shell CSG ✅; per-piece clipping (grooves baked before the split,
  inherited at seams) ✅; connector-safety (grooves clamped to the base top, so a
  shallow top-surface groove can't sever a full-height tab neck) ✅; ODbL
  attribution ✅. Inlay ribbons + base are partitioned **per piece** (complete,
  non-overlapping) and validated. Render mode is global per run.
- **Phase 7 — land cover (Tier 4)** ✅
  ESA WorldCover provider (S3 COG, no key) ✅ + local classified-raster upload ✅;
  class→filament mapping (explicit or auto top-N) ✅; top ~0.8 mm shell region
  splitting into named 3MF objects ✅; **per-piece** region clipping with a base
  body so each colour 3MF is a complete, non-overlapping printable model ✅;
  purge-waste guardrails (min-region drop + colour-change/region warnings) ✅;
  CC BY 4.0 attribution ✅. Optional Sentinel-2 NDVI adapter ⬜ (optional in the spec).

## Near-term next steps

- Verify the 3MF plate/project metadata by importing into real Bambu Studio.
