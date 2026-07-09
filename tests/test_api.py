"""API-level tests: job lifecycle, export blocking, download gating. No network."""

from __future__ import annotations

import json
import struct
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


def _glb_json(blob: bytes) -> dict:
    """Read a GLB's JSON chunk without trimesh, which does not convert axes."""
    json_len = struct.unpack("<I", blob[12:16])[0]
    return json.loads(blob[20 : 20 + json_len])


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


def test_preview_glb_is_y_up_with_flat_piece_nodes(geotiff_path):
    """glTF is a Y-up format; the pipeline is Z-up. The preview must convert.

    A 150 mm terrain is far wider than it is tall, so the up axis is the one
    with the smallest extent — and it must be Y, resting on the Y=0 plane.
    The conversion also has to be baked into the vertices: the web viewer
    slides pieces apart along their parent's X/Z, which only lands in the
    ground plane if the piece nodes carry no rotation of their own.
    """
    s = _run(_body(geotiff_path))
    r = client.get(f"/api/jobs/{s['id']}/preview.glb")
    assert r.status_code == 200
    gl = _glb_json(r.content)

    lo = [min(a) for a in zip(*(m["min"] for m in _positions(gl)))]
    hi = [max(a) for a in zip(*(m["max"] for m in _positions(gl)))]
    span = [h - low for h, low in zip(hi, lo)]
    assert span[1] < span[0] and span[1] < span[2], f"up axis is not Y: {span}"
    assert lo[1] == pytest.approx(0, abs=1e-6), "model does not rest on Y=0"

    pieces = gl["nodes"][1:]  # node 0 is trimesh's "world" root
    assert len(pieces) == 4
    assert all(n.get("matrix") is None for n in pieces), "rotation left on a node"


def _positions(gl: dict) -> list[dict]:
    return [
        gl["accessors"][m["primitives"][0]["attributes"]["POSITION"]]
        for m in gl["meshes"]
    ]


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
