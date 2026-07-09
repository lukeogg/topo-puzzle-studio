# CLAUDE.md

Guidance for working in this repo.

## What this is
TopoPuzzle Studio — a local web app + CLI that turns real elevation data into a
3D-printable topographic terrain model, optionally split into an interlocking
puzzle. Target printer: Bambu Lab P2S (0.4 mm nozzle, ~250 mm plate).

## Layout
- `packages/mesh` — the geometry core (installable `topopuzzle-mesh`), providers,
  and the `topopuzzle` CLI. **This is the heart; keep it coherent and tested.**
- `apps/api` — FastAPI: background jobs, SSE progress, GLB preview, ZIP download.
- `apps/web` — Next.js + React Three Fiber + MapLibre front end.
- `packages/shared` — shared TS types mirroring the API contract.
- `tests` — pytest, synthetic DEM fixtures, **no network**.
- `examples`, `docs`.

## Commands
```bash
make setup          # venv + Python core/API + web deps
make dev            # API :8000 + web :3000
make test           # pytest (must stay green)
make lint           # ruff
make examples       # regenerate examples/*.zip from synthetic DEMs
source .venv/bin/activate && topopuzzle generate --geotiff f.tif -o out.zip
```

## Non-negotiables (enforced by tests/validation)
- Every exported mesh is **watertight + manifold + positive volume** (re-checked
  independently in `validate.py`, not just trusted from CSG).
- **mm dimensions are true**: reproject to local UTM before meshing.
- Min feature ≥ 1.2 mm; build-volume fit; overhang and print-in-place gap warnings.
- Connector geometry is **original + parametric** (`connectors.py`); print-in-place
  uses straight-walled tabs only (no undercuts).

## Pipeline (packages/mesh)
`providers → ElevationGrid → dem (reproject/resample/fill/smooth/water/normalize)
→ terrain (watertight solid) → puzzle (exact tessellation + per-piece CSG) →
validate → export (STL/OBJ/3MF + ZIP)`. Orchestrated by `pipeline.generate()`.

## Conventions
- Deterministic: no randomness; connector alternation is seeded. Keep it that way.
- Add a test with every geometry change; run `make test` before committing.
- Network providers are optional and never required by CI.
- Roadmap / phase status: `docs/roadmap.md`. Phases 1–3 done, 4–5 partial, 6–7 planned.
