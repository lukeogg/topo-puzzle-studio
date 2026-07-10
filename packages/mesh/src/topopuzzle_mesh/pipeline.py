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


def load_overlay_features(settings: GenerateSettings):
    """Load Tier-3 overlay features: local GeoJSON if given, else Overpass."""
    ov = settings.overlays
    if not ov.enabled:
        return None
    if ov.geojson_path:
        from .providers.osm import load_geojson_features

        return load_geojson_features(ov.geojson_path)
    if settings.bounds is None:
        return None
    from .providers.osm import OverpassProvider

    return OverpassProvider().fetch(settings.bounds, ov.classes)


def load_landcover_grid(settings: GenerateSettings):
    """Load a Tier-4 land-cover grid: local classified raster, else WorldCover."""
    lc = settings.landcover
    if not lc.enabled:
        return None
    if lc.raster_path:
        from .providers.landcover import LocalLandCoverProvider

        return LocalLandCoverProvider(lc.raster_path).get_landcover_grid(settings.bounds)
    if settings.bounds is None:
        return None
    from .providers.landcover import WorldCoverProvider

    return WorldCoverProvider().get_landcover_grid(settings.bounds)


def generate(
    settings: GenerateSettings,
    grid: ElevationGrid | None = None,
    progress: Progress = _noop,
    features=None,
    landcover=None,
) -> GenerationOutput:
    """Run the full pipeline, optionally with a pre-loaded grid (tests/uploads)."""
    if grid is None:
        grid = load_grid(settings, progress)

    progress("processing", 0.2)
    progress("terrain", 0.4)
    if features is None and settings.overlays.enabled:
        features = load_overlay_features(settings)
    if landcover is None and settings.landcover.enabled:
        landcover = load_landcover_grid(settings)
    progress("splitting", 0.55)
    result = split_puzzle(grid, settings, features=features, landcover=landcover)

    progress("validating", 0.8)
    report = validate(result)

    progress("packaging", 0.95)
    return GenerationOutput(result=result, report=report, grid=grid)


__all__ = ["generate", "load_grid", "GenerationOutput", "Bounds", "STAGES"]
