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
- **Phase 5 — 3MF + color Tier 2** 🟡
  3MF named objects in mm at printable transforms ✅ (Bambu plate metadata
  best-effort, verify in Bambu Studio). Per-band contour meshes ✅ (Tier-2 colour:
  `model-banded.3mf`, CSG-exact slab partition). Magnet pockets ⬜,
  advanced puzzle styles (organic/Voronoi) ⬜.
- **Phase 6 — OSM overlays (Tier 3)** ⬜
  Overpass adapter + GeoJSON upload, drape/buffer, deboss/emboss/inlay, per-piece
  clipping, connector-safety checks.
- **Phase 7 — land cover (Tier 4)** ⬜
  ESA WorldCover provider + classified-raster upload, class→filament mapping, top-shell
  region splitting, purge-waste guardrails; optional Sentinel-2 NDVI adapter.

## Near-term next steps

- Verify the 3MF plate/project metadata by importing into real Bambu Studio.
- Tray split-halves with alignment pins when the tray exceeds the plate.
- Organic/Voronoi connector styles behind the same `ConnectorSettings` seam API.
