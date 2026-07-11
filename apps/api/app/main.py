"""FastAPI application: jobs, SSE progress, GLB preview, ZIP download."""

from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from topopuzzle_mesh.config import GenerateSettings
from topopuzzle_mesh.providers import LocalGeoTIFFProvider

from .geocode import default_geocoder
from .jobs import manager

app = FastAPI(title="TopoPuzzle Studio API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_UPLOADS: dict[str, str] = {}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/uploads")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """Store an uploaded file (GeoTIFF DEM, classified raster, or GeoJSON) and
    return an id to reference in a job.  The original suffix is preserved so
    rasterio/JSON loaders see the extension they expect."""
    upload_id = uuid.uuid4().hex[:12]
    suffix = Path(file.filename or "").suffix or ".bin"
    dest = Path(tempfile.gettempdir()) / f"tpz-upload-{upload_id}{suffix}"
    with open(dest, "wb") as f:
        f.write(await file.read())
    _UPLOADS[upload_id] = str(dest)
    return {"upload_id": upload_id}


def _resolve_upload(value: str | None) -> str | None:
    """Map an upload id to its stored path (pass through absolute paths)."""
    if not value:
        return value
    return _UPLOADS.get(value, value)


@app.post("/api/jobs")
def create_job(settings: GenerateSettings) -> dict:
    """Start a generation job.  ``geotiff_path`` / overlay GeoJSON / land-cover
    raster may each be an upload id returned by /api/uploads or an absolute path."""
    grid = None
    if settings.provider == "geotiff":
        path = _resolve_upload(settings.geotiff_path)
        if not path or not Path(path).exists():
            raise HTTPException(400, "geotiff provider requires a valid upload_id or path")
        settings = settings.model_copy(update={"geotiff_path": path})
        grid = LocalGeoTIFFProvider(path).get_elevation_grid(settings.bounds)
    elif settings.bounds is None:
        raise HTTPException(400, "bounds are required for network providers")

    # Resolve overlay / land-cover upload ids to stored paths.
    if settings.overlays.geojson_path:
        settings = settings.model_copy(update={
            "overlays": settings.overlays.model_copy(
                update={"geojson_path": _resolve_upload(settings.overlays.geojson_path)}
            )
        })
    if settings.landcover.raster_path:
        settings = settings.model_copy(update={
            "landcover": settings.landcover.model_copy(
                update={"raster_path": _resolve_upload(settings.landcover.raster_path)}
            )
        })

    job = manager.create(settings, grid=grid)
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.public()


@app.get("/api/jobs/{job_id}/stream")
async def job_stream(job_id: str) -> StreamingResponse:
    job = manager.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")

    async def gen():
        last = None
        while True:
            snap = job.public()
            key = (snap["status"], snap["stage"], round(snap["progress"], 3))
            if key != last:
                yield f"data: {json.dumps(snap)}\n\n"
                last = key
            if snap["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/preview.glb")
def job_preview(job_id: str) -> FileResponse:
    job = manager.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "preview not ready")
    return FileResponse(job.dir / "preview.glb", media_type="model/gltf-binary")


@app.get("/api/jobs/{job_id}/download")
def job_download(job_id: str) -> FileResponse:
    job = manager.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "download not ready")
    if not job.exportable:
        raise HTTPException(
            409, "export blocked by hard validation errors — fix the settings and regenerate"
        )
    return FileResponse(
        job.dir / "puzzle.zip",
        media_type="application/zip",
        filename="topopuzzle.zip",
    )


@app.get("/api/geocode")
def geocode(q: str, limit: int = 8) -> list[dict]:
    """Structured place search (Nominatim → Photon fallback), cached.

    Optional/online — returns [] on any failure so the UI degrades gracefully.
    Each result carries name/short_name/lat/lon/bbox plus kind, category,
    importance, and which provider answered.
    """
    limit = max(1, min(limit, 15))
    return [p.as_dict() for p in default_geocoder.search(q, limit=limit)]
