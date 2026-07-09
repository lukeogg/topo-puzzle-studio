"""TopoPuzzle Studio geometry core, providers, and CLI."""

from __future__ import annotations

from .config import (
    AssemblyMode,
    Bounds,
    ConnectorSettings,
    ConnectorStyle,
    GenerateSettings,
)
from .elevation import Attribution, ElevationGrid
from .pipeline import GenerationOutput, generate, load_grid
from .puzzle import Piece, PuzzleResult, split_puzzle
from .terrain import TerrainResult, build_terrain
from .validate import ValidationReport, validate

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AssemblyMode",
    "Bounds",
    "ConnectorSettings",
    "ConnectorStyle",
    "GenerateSettings",
    "Attribution",
    "ElevationGrid",
    "GenerationOutput",
    "generate",
    "load_grid",
    "Piece",
    "PuzzleResult",
    "split_puzzle",
    "TerrainResult",
    "build_terrain",
    "ValidationReport",
    "validate",
]
