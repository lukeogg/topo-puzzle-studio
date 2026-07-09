"""In-memory background job manager.

A job runs the geometry pipeline on a worker thread, streaming stage/progress
updates that the API surfaces over SSE.  Results (ZIP + GLB preview) are written
to a per-job temp directory.
"""

from __future__ import annotations

import tempfile
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from topopuzzle_mesh.config import GenerateSettings
from topopuzzle_mesh.export import finalize_pieces, package_zip
from topopuzzle_mesh.pipeline import generate

# A warm, distinguishable palette for preview pieces (RGBA 0-255).
_PALETTE = [
    (61, 107, 72), (168, 61, 19), (205, 191, 166), (138, 127, 104),
    (216, 83, 31), (122, 141, 90), (160, 150, 110), (110, 102, 86),
]


@dataclass
class Job:
    id: str
    settings: GenerateSettings
    grid: object | None = None  # pre-loaded ElevationGrid (uploads)
    status: str = "queued"  # queued | running | done | error
    stage: str = "queued"
    progress: float = 0.0
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    report: dict | None = None
    footprint_mm: tuple[float, float] | None = None
    piece_count: int = 0
    dir: Path | None = None

    def public(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "error": self.error,
            "warnings": self.warnings,
            "report": self.report,
            "footprint_mm": self.footprint_mm,
            "piece_count": self.piece_count,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def create(self, settings: GenerateSettings, grid=None) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], settings=settings, grid=grid)
        job.dir = Path(tempfile.mkdtemp(prefix=f"tpz-{job.id}-"))
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def _run(self, job: Job) -> None:
        job.status = "running"
        try:
            def prog(stage: str, frac: float) -> None:
                job.stage, job.progress = stage, float(frac)

            out = generate(job.settings, grid=job.grid, progress=prog)
            job.report = out.report.as_dict()
            job.warnings = out.report.warnings + out.result.warnings
            job.footprint_mm = out.result.assembled_footprint_mm
            job.piece_count = len(out.result.pieces)

            package_zip(out.result, out.report, str(job.dir / "puzzle.zip"))
            _write_glb(out.result, job.dir / "preview.glb")

            job.stage, job.progress, job.status = "done", 1.0, "done"
        except Exception as exc:  # pragma: no cover - surfaced to the client
            job.status = "error"
            job.error = f"{exc}"
            traceback.print_exc()


def _write_glb(result, path: Path) -> None:
    """Assembled preview: each piece a distinctly-coloured object in one GLB."""
    scene = trimesh.Scene()
    for i, (label, mesh) in enumerate(finalize_pieces(result)):
        m = mesh.copy()
        color = np.array([*_PALETTE[i % len(_PALETTE)], 255], dtype=np.uint8)
        m.visual.vertex_colors = np.tile(color, (len(m.vertices), 1))
        scene.add_geometry(m, node_name=label, geom_name=label)
    scene.export(str(path), file_type="glb")


manager = JobManager()
