# topopuzzle-mesh

Geometry core, data providers, and CLI for **TopoPuzzle Studio**.

This package turns a Digital Elevation Model (DEM) into a watertight, 3D-printable
topographic terrain model, optionally split into a multi-piece puzzle with
parametric tab/socket connectors.

It is pure-Python and installs from prebuilt arm64 wheels (no GDAL/Homebrew build step).

See the repository root README for setup and the full product documentation.

## Modules

- `elevation` — the `ElevationGrid` value object (array + CRS + attribution).
- `dem` — crop / resample / fill / normalize / exaggerate / smooth / water-flatten.
- `terrain` — build a watertight terrain solid from an elevation grid.
- `puzzle` — grid split with parametric connectors, `separate-pieces` / `print-in-place`.
- `connectors` — original parametric tab/socket connector geometry.
- `validate` — watertight / manifold / min-feature / build-volume / overhang checks.
- `labels`, `tray` — embossed underside labels and optional tray/frame.
- `color` — elevation-band `color-changes.txt` (Tier-1 AMS color).
- `export` — STL / OBJ / 3MF writers and the ZIP packager.
- `providers` — `LocalGeoTIFFProvider`, `TerrainTilesProvider`.
- `cli` — the `topopuzzle` command.
