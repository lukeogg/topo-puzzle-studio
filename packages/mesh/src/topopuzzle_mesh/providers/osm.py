"""OSM vector feature provider (Tier-3 overlays).

Two ways in, same output — a list of :class:`OsmFeature` (class + geometry in
lon/lat):

* :class:`OverpassProvider` queries the Overpass API for a bbox, filtered to the
  requested feature classes.  Optional/online; a ``session`` can be injected for
  offline tests.
* :func:`load_geojson_features` reads a local GeoJSON file — the network-free
  alternative — classifying by an explicit ``class`` property or OSM-style tags.

OSM data is ODbL — using overlays adds an attribution requirement (handled in the
export manifest).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..config import OverlayClass

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Overpass tag filters and the geometry kind each class produces.
_CLASS_FILTERS = {
    OverlayClass.ROADS: ('way["highway"~"^(motorway|trunk|primary|secondary)$"]', "line"),
    OverlayClass.TRAILS: ('way["highway"~"^(path|footway|track|bridleway)$"]', "line"),
    OverlayClass.WATERWAYS: ('way["waterway"~"^(river|stream|canal)$"]', "line"),
    OverlayClass.LAKES: ('way["natural"="water"]', "polygon"),
}


@dataclass(frozen=True)
class OsmFeature:
    osm_class: OverlayClass
    geom_type: str  # "line" | "polygon"
    coords: tuple[tuple[float, float], ...]  # (lon, lat) vertices


def build_overpass_query(bounds, classes) -> str:
    """Overpass QL for the requested classes over ``bounds`` (returns geometry)."""
    bbox = f"{bounds.south},{bounds.west},{bounds.north},{bounds.east}"
    parts = []
    for c in classes:
        flt = _CLASS_FILTERS.get(c)
        if flt:
            parts.append(f"  {flt[0]}({bbox});")
    body = "\n".join(parts)
    return f"[out:json][timeout:90];\n(\n{body}\n);\nout geom;"


def _classify(tags: dict) -> tuple[OverlayClass, str] | None:
    hw = tags.get("highway")
    if hw in ("motorway", "trunk", "primary", "secondary"):
        return OverlayClass.ROADS, "line"
    if hw in ("path", "footway", "track", "bridleway"):
        return OverlayClass.TRAILS, "line"
    if tags.get("waterway") in ("river", "stream", "canal"):
        return OverlayClass.WATERWAYS, "line"
    if tags.get("natural") == "water":
        return OverlayClass.LAKES, "polygon"
    return None


def parse_overpass(data: dict) -> list[OsmFeature]:
    out: list[OsmFeature] = []
    for el in data.get("elements", []):
        geom = el.get("geometry")
        if el.get("type") != "way" or not geom:
            continue
        cls = _classify(el.get("tags", {}))
        if cls is None:
            continue
        coords = tuple((g["lon"], g["lat"]) for g in geom if "lon" in g and "lat" in g)
        if len(coords) >= 2:
            out.append(OsmFeature(osm_class=cls[0], geom_type=cls[1], coords=coords))
    return out


class OverpassProvider:
    name = "overpass"

    def __init__(self, session=None, url: str = OVERPASS_URL):
        self._session = session
        self.url = url

    def fetch(self, bounds, classes) -> list[OsmFeature]:
        import requests

        sess = self._session or requests.Session()
        query = build_overpass_query(bounds, classes)
        resp = sess.post(self.url, data={"data": query}, timeout=120)
        resp.raise_for_status()
        return parse_overpass(resp.json())


def _class_from_props(props: dict) -> tuple[OverlayClass, str] | None:
    explicit = props.get("class")
    if explicit:
        try:
            c = OverlayClass(explicit)
            kind = "polygon" if c is OverlayClass.LAKES else "line"
            return c, kind
        except ValueError:
            pass
    return _classify(props)


def _rings(geometry) -> list[tuple[str, list]]:
    """Yield (kind, coords) for the drawable parts of a GeoJSON geometry."""
    gtype = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if gtype == "LineString":
        return [("line", coords)]
    if gtype == "MultiLineString":
        return [("line", line) for line in coords]
    if gtype == "Polygon":
        return [("polygon", coords[0])] if coords else []
    if gtype == "MultiPolygon":
        return [("polygon", poly[0]) for poly in coords if poly]
    return []


def load_geojson_features(path: str, default_class: OverlayClass = OverlayClass.ROADS) -> list[OsmFeature]:
    """Read overlay features from a GeoJSON FeatureCollection."""
    with open(path) as f:
        data = json.load(f)
    out: list[OsmFeature] = []
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        classified = _class_from_props(props)
        for kind, ring in _rings(feat.get("geometry") or {}):
            if classified is not None:
                cls = classified[0]
            else:
                cls = OverlayClass.LAKES if kind == "polygon" else default_class
            coords = tuple((c[0], c[1]) for c in ring if len(c) >= 2)
            need = 3 if kind == "polygon" else 2
            if len(coords) >= need:
                out.append(OsmFeature(osm_class=cls, geom_type=kind, coords=coords))
    return out
