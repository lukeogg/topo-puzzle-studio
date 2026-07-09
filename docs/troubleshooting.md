# Troubleshooting

## Setup (macOS / Apple Silicon)

**`make setup` fails building a geospatial wheel.** All deps (rasterio, pyproj,
shapely, trimesh, manifold3d, scipy) ship prebuilt arm64 wheels — no Homebrew GDAL
needed. Ensure you're on Python 3.11+ and a recent `pip`/`uv`. `uv venv --python 3.11`
then re-run. If a specific dep has no arm64 wheel on your Python version, try 3.11.

**`topopuzzle: command not found`.** Activate the venv: `source .venv/bin/activate`,
or call it via `make cli ARGS='…'`.

## Generation

**"connector neck below 1.2 mm minimum".** The tabs are too small at your physical
scale. Increase `--size-mm`, use fewer pieces, or widen tabs
(`ConnectorSettings.width_frac`). This is an error, not a warning — thin necks snap.

**"a piece exceeds the 250 × 250 mm plate".** Reduce `--size-mm` or add pieces so each
piece fits. For print-in-place, the *assembled* model must fit one plate; switch to
separate-pieces to print pieces individually.

**"pieces as close as … mm (< gap)".** Print-in-place gap too small; walls will fuse.
Raise `--gap-mm` to ≥ 0.4 (never below 0.3).

**"max terrain slope is near-vertical/overhanging".** High exaggeration or real cliffs.
Lower `--z-exaggeration`, enable Gaussian smoothing, or print with supports.

**"nodata … exceeds tolerance".** The DEM has large holes that were interpolated.
Pick a smaller/different area or a better source; interpolated regions are approximate.

## Web app

**Map is blank / grey.** No `NEXT_PUBLIC_MAP_STYLE` set → the app uses its offline
cartographic fallback on purpose (no third-party tile dependency). Set a MapLibre
style URL to see basemap tiles. Elevation still works regardless of the map style.

**3D preview never loads.** It appears only after a job finishes. Check the API is
running on `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`) and watch the
progress pipeline / browser console for the job status.

**CORS errors.** The API allows `localhost:3000` by default; if you run the web app on
another port, add it to `allow_origins` in `apps/api/app/main.py`.

## Slicing

**Pieces too tight/loose.** Print `coupon.stl` and adjust `--clearance-mm` (separate)
or `--gap-mm` (print-in-place) by 0.05 mm steps, then regenerate. See the
[print guide](print-guide.md).
