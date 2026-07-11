# Data providers

Elevation providers implement one interface:

```python
get_elevation_grid(bounds, target_resolution_m, crs) -> ElevationGrid
```

`ElevationGrid` carries the elevation array, CRS, resolution, nodata mask, provider
name, upstream source names, attribution/license text, and (where available) a data
timestamp/version. Map tiles and elevation data are **separate concerns** — the map
UI's tile style is independent of the DEM provider.

## Priority / status

1. **Local GeoTIFF** — ✅ implemented. Fully offline MVP path. Any single-band
   elevation GeoTIFF; reprojected to local UTM before meshing. `--geotiff path.tif`.
2. **AWS/Mapzen Terrain Tiles (terrarium PNG)** — ✅ implemented. No API key, global.
   Online default. Elevation decoded from the RGB terrarium encoding
   (`R*256 + G + B/256 - 32768`). Upstream attribution (SRTM, USGS 3DEP, ETOPO1,
   GMTED2010, national DEMs) is preserved — not merely "AWS Terrain Tiles".
   `--provider terrain-tiles --bbox W,S,E,N`.
3. **USGS 3DEP** — ✅ implemented. High-quality U.S. DEM via The National Map's
   dynamic `3DEPElevation` ImageServer `exportImage` (float32 GeoTIFF, no key).
   U.S. coverage only; out-of-coverage cells return as nodata.
   `--provider usgs-3dep --bbox W,S,E,N`.
4. **OpenTopography** — ✅ implemented. Global DEM `globaldem` REST API; **requires
   an API key** (`api_key=` or `OPENTOPOGRAPHY_API_KEY`). Pick a dataset with
   `OpenTopographyProvider(demtype=...)` (default `SRTMGL1`; also `AW3D30`, `COP30`,
   `NASADEM`, …). Public endpoint enforces an area cap — keep selections modest.
   `--provider opentopography --bbox W,S,E,N`.
5. **OpenTopoData** — ✅ implemented, small-area/preview only. It is a point-lookup
   API; dense grids would need excessive sampling against the public instance, so the
   total sample count is **capped** (default 100 points) and the grid resolution is
   reduced to fit. Point `base_url` at a self-hosted instance and raise `max_points`
   to lift the ceiling; pick the dataset with `OpenTopoDataProvider(dataset=...)`
   (default `aster30m`). Ocean/out-of-coverage points return null and are carried
   through as nodata. `--provider opentopodata --bbox W,S,E,N`.

## Adding a provider

Create a class with a `name` attribute and a `get_elevation_grid(...)` method
returning an `ElevationGrid` with a fully populated `Attribution`, then register it in
`packages/mesh/src/topopuzzle_mesh/providers/__init__.py::get_provider`.

Network providers are **optional** and skipped in CI (tests use synthetic fixtures and
local GeoTIFFs only).

## Map tile style (frontend)

The map UI reads `NEXT_PUBLIC_MAP_STYLE` (a MapLibre style URL). If unset it falls
back to an offline cartographic style so the app works with no network and no
third-party tile dependency. **Do not** point it at public OSM tile servers as a
production default — OSM's tile usage policy prohibits treating them as a free CDN.
Use your own provider (MapTiler, Stadia, self-hosted, etc.) and keep its attribution
visible.
