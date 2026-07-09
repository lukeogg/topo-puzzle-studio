"""API-level tests: job lifecycle, export blocking, download gating. No network."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

fastapi_testclient = pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _run(body: dict, timeout: float = 30.0) -> dict:
    jid = client.post("/api/jobs", json=body).json()["job_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = client.get(f"/api/jobs/{jid}").json()
        if s["status"] in ("done", "error"):
            return {"id": jid, **s}
        time.sleep(0.2)
    raise TimeoutError("job did not finish")


def _body(geotiff_path: str, **over) -> dict:
    b = {
        "provider": "geotiff", "geotiff_path": geotiff_path,
        "rows": 2, "cols": 2, "size_mm": 150, "base_mm": 3.0,
        "z_exaggeration": 1.8, "assembly": "separate-pieces", "gap_mm": 0.4,
        "max_grid": 120, "smoothing_sigma": 0, "labels": False,
        "water": {"enabled": False, "threshold_m": 0}, "formats": ["stl", "3mf"],
    }
    b.update(over)
    return b


def test_health():
    assert client.get("/api/health").json()["ok"] is True


def test_job_success_is_exportable_and_downloadable(geotiff_path):
    s = _run(_body(geotiff_path))
    assert s["status"] == "done"
    assert s["exportable"] is True
    assert s["report"]["has_errors"] is False
    r = client.get(f"/api/jobs/{s['id']}/download")
    assert r.status_code == 200
    assert len(r.content) > 1000


def test_oversized_job_blocks_export(geotiff_path):
    # 900 mm on a 250 mm plate -> hard build-volume error -> export blocked.
    s = _run(_body(geotiff_path, size_mm=900, formats=["stl"]))
    assert s["status"] == "done"  # completes, not errored
    assert s["exportable"] is False
    assert s["report"]["has_errors"] is True
    assert client.get(f"/api/jobs/{s['id']}/download").status_code == 409


def test_geotiff_requires_valid_path():
    r = client.post("/api/jobs", json=_body("/nonexistent/does-not-exist.tif"))
    assert r.status_code == 400
