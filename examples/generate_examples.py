"""Generate committed example outputs from synthetic DEMs (no network).

Run:  python examples/generate_examples.py
"""

from __future__ import annotations

import pathlib

from topopuzzle_mesh import dem
from topopuzzle_mesh.config import AssemblyMode, GenerateSettings
from topopuzzle_mesh.export import package_zip
from topopuzzle_mesh.pipeline import generate

HERE = pathlib.Path(__file__).parent


def main() -> None:
    cases = [
        ("hill-solid", dict(rows=1, cols=1, size_mm=120), "hill"),
        ("hill-3x3-separate", dict(rows=3, cols=3, size_mm=160, labels=True), "hill"),
        ("coastal-2x2-pip", dict(rows=2, cols=2, size_mm=140,
                                 assembly=AssemblyMode.PRINT_IN_PLACE), "coastal"),
    ]
    for name, kw, fixture in cases:
        grid = dem.fixture(fixture, 100)
        settings = GenerateSettings(max_grid=140, **kw)
        out = generate(settings, grid=grid)
        dest = HERE / f"{name}.zip"
        package_zip(out.result, out.report, str(dest))
        status = "errors" if out.report.has_errors else "ok"
        print(f"{name:24} pieces={len(out.result.pieces):2d}  {status}  -> {dest.name}")


if __name__ == "__main__":
    main()
