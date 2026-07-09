"""End-to-end generation orchestrator with progress reporting.

Stages mirror the UX spec: fetching DEM → processing raster → generating terrain
→ splitting pieces → validating → packaging.  A ``progress`` callback lets the
API stream SSE updates; the CLI passes a Rich-backed callback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .config import Bounds, GenerateSettings
from .elevation import ElevationGrid
from .providers import get_provider
from .puzzle import PuzzleResult, split_puzzle
from .validate import ValidationReport, validate

Progress = Callable[[str, float], None]  # (stage, fraction 0..1)

STAGES = [
    ("fetching", "Fetching DEM"),
    ("processing", "Processing raster"),
    ("terrain", "Generating terrain"),
    ("splitting", "Splitting pieces"),
    ("validating", "Validating"),
    ("packaging", "Packaging"),
]


@dataclass
class GenerationOutput:
    result: PuzzleResult
    report: ValidationReport
    grid: ElevationGrid


def _noop(stage: str, frac: float) -> None:  # pragma: no cover
    pass


def load_grid(settings: GenerateSettings, progress: Progress = _noop) -> ElevationGrid:
    progress("fetching", 0.0)
    provider = get_provider(settings.provider, geotiff_path=settings.geotiff_path)
    # Resolution target derived from footprint / max_grid.
    if settings.bounds is not None:
        b = settings.bounds
        span_m = max((b.east - b.west), (b.north - b.south)) * 111_000.0
        target_res = max(span_m / settings.max_grid, 10.0)
        grid = provider.get_elevation_grid(b, target_res)
    else:
        grid = provider.get_elevation_grid(None)  # geotiff full extent
    progress("fetching", 1.0)
    return grid


def generate(
    settings: GenerateSettings,
    grid: ElevationGrid | None = None,
    progress: Progress = _noop,
) -> GenerationOutput:
    """Run the full pipeline, optionally with a pre-loaded grid (tests/uploads)."""
    if grid is None:
        grid = load_grid(settings, progress)

    progress("processing", 0.2)
    progress("terrain", 0.4)
    progress("splitting", 0.55)
    result = split_puzzle(grid, settings)

    progress("validating", 0.8)
    report = validate(result)

    progress("packaging", 0.95)
    return GenerationOutput(result=result, report=report, grid=grid)


__all__ = ["generate", "load_grid", "GenerationOutput", "Bounds", "STAGES"]
