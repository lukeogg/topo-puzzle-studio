"""Tier-3 OSM overlays: providers, draping, render modes, filtering. No network."""

from __future__ import annotations

import io
import json
import zipfile

import trimesh

from topopuzzle_mesh.config import (
    GenerateSettings,
    OverlayClass,
    OverlaySettings,
    RenderMode,
)
from topopuzzle_mesh.export import attribution_text, package_zip
from topopuzzle_mesh.pipeline import generate
from topopuzzle_mesh.providers.osm import (
    OsmFeature,
    OverpassProvider,
    build_overpass_query,
    load_geojson_features,
    parse_overpass,
)
from topopuzzle_mesh.puzzle import split_puzzle

# A lake near the fixture's high centre (deboss there actually removes material),
# and a diagonal line across it.
LAKE = OsmFeature(
    OverlayClass.LAKES, "polygon",
    ((-111.82, 48.58), (-111.78, 48.58), (-111.78, 48.62), (-111.82, 48.62)),
)
ROAD = OsmFeature(
    OverlayClass.ROADS, "line", ((-111.86, 48.55), (-111.74, 48.65)),
)


def _solid(**over):
    return GenerateSettings(size_mm=180, rows=1, cols=1, max_grid=100, **over)


# --- providers ------------------------------------------------------------- #


def test_parse_overpass_classifies_ways():
    data = {
        "elements": [
            {"type": "way", "tags": {"highway": "primary"},
             "geometry": [{"lat": 48.5, "lon": -111.9}, {"lat": 48.6, "lon": -111.8}]},
            {"type": "way", "tags": {"natural": "water"},
             "geometry": [{"lat": 48.5, "lon": -111.9}, {"lat": 48.6, "lon": -111.9},
                          {"lat": 48.6, "lon": -111.8}]},
            {"type": "node", "lat": 48.5, "lon": -111.9},  # ignored
        ]
    }
    feats = parse_overpass(data)
    classes = {f.osm_class for f in feats}
    assert classes == {OverlayClass.ROADS, OverlayClass.LAKES}


def test_overpass_query_mentions_bbox_and_classes():
    from topopuzzle_mesh.config import Bounds

    q = build_overpass_query(
        Bounds(west=-111.9, south=48.5, east=-111.7, north=48.7),
        [OverlayClass.ROADS, OverlayClass.LAKES],
    )
    assert "48.5,-111.9,48.7,-111.7" in q
    assert "highway" in q and "natural" in q


def test_overpass_provider_offline():
    from topopuzzle_mesh.config import Bounds

    payload = {
        "elements": [
            {"type": "way", "tags": {"waterway": "river"},
             "geometry": [{"lat": 48.5, "lon": -111.9}, {"lat": 48.6, "lon": -111.8}]},
        ]
    }

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    class FakeSession:
        def post(self, url, data=None, timeout=0):
            assert "data" in data
            return FakeResp()

    prov = OverpassProvider(session=FakeSession())
    feats = prov.fetch(Bounds(west=-111.9, south=48.5, east=-111.7, north=48.7), [OverlayClass.WATERWAYS])
    assert len(feats) == 1 and feats[0].osm_class is OverlayClass.WATERWAYS


def test_geojson_loader(tmp_path):
    gj = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"class": "roads"},
             "geometry": {"type": "LineString", "coordinates": [[-111.86, 48.55], [-111.74, 48.65]]}},
            {"type": "Feature", "properties": {"natural": "water"},
             "geometry": {"type": "Polygon", "coordinates": [[[-111.82, 48.58], [-111.78, 48.58],
                                                              [-111.78, 48.62], [-111.82, 48.62], [-111.82, 48.58]]]}},
        ],
    }
    p = tmp_path / "features.geojson"
    p.write_text(json.dumps(gj))
    feats = load_geojson_features(str(p))
    assert {f.osm_class for f in feats} == {OverlayClass.ROADS, OverlayClass.LAKES}


# --- draping / render modes ------------------------------------------------ #


def test_deboss_removes_and_emboss_adds_material(hill_grid):
    base = split_puzzle(hill_grid, _solid()).pieces[0].mesh.volume

    deb = OverlaySettings(enabled=True, render=RenderMode.DEBOSS, classes=[OverlayClass.LAKES])
    v_deb = split_puzzle(hill_grid, _solid(overlays=deb), features=[LAKE]).pieces[0].mesh
    assert v_deb.is_watertight and v_deb.volume < base

    emb = OverlaySettings(enabled=True, render=RenderMode.EMBOSS, classes=[OverlayClass.LAKES])
    v_emb = split_puzzle(hill_grid, _solid(overlays=emb), features=[LAKE]).pieces[0].mesh
    assert v_emb.is_watertight and v_emb.volume > base


def test_inlay_produces_complete_watertight_partition(hill_grid):
    ov = OverlaySettings(enabled=True, render=RenderMode.INLAY, classes=[OverlayClass.LAKES], relief_mm=0.6)
    res = split_puzzle(hill_grid, _solid(overlays=ov), features=[LAKE])
    names = [n for n, _, _ in res.overlay_objects]
    assert any("inlay-lakes" in n for n in names)  # a flush inlay ribbon
    assert any(n.endswith("-base") for n in names)  # and the base body (complete)
    for name, mesh, hexc in res.overlay_objects:
        assert mesh.is_watertight and mesh.volume > 0, name
    # base + inlay partition the whole piece (flush, no missing/overlapping volume).
    piece_vol = split_puzzle(hill_grid, _solid()).pieces[0].mesh.volume
    total = sum(m.volume for _, m, _ in res.overlay_objects)
    assert abs(total - piece_vol) / piece_vol < 0.02


def test_overlays_clip_per_piece_and_stay_watertight(hill_grid):
    ov = OverlaySettings(enabled=True, render=RenderMode.DEBOSS,
                         classes=[OverlayClass.ROADS], width_scale=20.0)
    s = GenerateSettings(size_mm=180, rows=2, cols=2, max_grid=100, overlays=ov)
    res = split_puzzle(hill_grid, s, features=[ROAD])
    assert len(res.pieces) == 4
    # No drop warning (the scaled road ribbon clears the minimum), and every
    # piece is still watertight after inheriting the baked-in groove.
    assert not any("dropped" in w for w in res.warnings)
    assert all(p.mesh.is_watertight and p.mesh.volume > 0 for p in res.pieces)


def test_thin_line_class_is_dropped_with_warning(hill_grid):
    ov = OverlaySettings(enabled=True, render=RenderMode.DEBOSS,
                         classes=[OverlayClass.TRAILS], min_width_mm=1.0, width_scale=1.0)
    res = split_puzzle(hill_grid, _solid(overlays=ov),
                       features=[OsmFeature(OverlayClass.TRAILS, "line", ROAD.coords)])
    assert any("dropped" in w for w in res.warnings)


# --- export ---------------------------------------------------------------- #


def test_inlay_objects_and_odbl_in_export(hill_grid):
    ov = OverlaySettings(enabled=True, render=RenderMode.INLAY, classes=[OverlayClass.LAKES])
    out = generate(_solid(overlays=ov), grid=hill_grid, features=[LAKE])
    assert "OpenStreetMap" in attribution_text(out.result)
    package_zip(out.result, out.report, "/tmp/_test_overlays.zip")
    z = zipfile.ZipFile("/tmp/_test_overlays.zip")
    assert "model-overlays.3mf" in z.namelist()
    scene = trimesh.load(io.BytesIO(z.read("model-overlays.3mf")), file_type="3mf")
    assert len(scene.geometry) >= 1
