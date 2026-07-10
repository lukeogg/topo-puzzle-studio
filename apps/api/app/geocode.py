"""Place search (geocoding) for the map UI.

Wraps two OpenStreetMap-based geocoders — Nominatim as primary, Photon as a
fallback — behind one interface that returns *structured* results (name, kind,
category, importance, bbox) rather than a bare lat/lon.  Results are cached
in-memory so repeated or superseded searches don't re-hit the upstream service,
which matters because Nominatim's public instance rate-limits aggressively.

Both providers are optional/online; every failure degrades to the next provider
and finally to an empty list, so the UI keeps working offline.  A ``session`` can
be injected for offline testing (the whole module makes no network calls when the
session is faked).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_URL = "https://photon.komoot.io/api"
_USER_AGENT = "TopoPuzzleStudio/0.1 (local tool)"


@dataclass(frozen=True)
class Place:
    """One geocoding hit, normalised across providers."""

    name: str  # full display name
    lat: float
    lon: float
    bbox: dict | None  # {south, north, west, east} or None
    short_name: str = ""  # concise label (e.g. "Denver")
    kind: str = ""  # feature type: city, peak, park, water, …
    category: str = ""  # OSM class: place, natural, boundary, …
    importance: float = 0.0  # 0..1 rank for ordering
    source: str = ""  # which provider answered

    def as_dict(self) -> dict:
        return asdict(self)


def _bbox_from_nominatim(bb) -> dict | None:
    # Nominatim boundingbox is [south, north, west, east] as strings.
    if not bb or len(bb) != 4:
        return None
    return {
        "south": float(bb[0]), "north": float(bb[1]),
        "west": float(bb[2]), "east": float(bb[3]),
    }


def _bbox_from_photon(extent) -> dict | None:
    # Photon extent is [west, north, east, south].
    if not extent or len(extent) != 4:
        return None
    w, n, e, s = extent
    return {"south": float(s), "north": float(n), "west": float(w), "east": float(e)}


class Geocoder:
    def __init__(self, session=None, cache_size: int = 256, timeout: float = 8.0):
        self._session = session
        self._timeout = timeout
        self._cache: OrderedDict[tuple[str, int], list[Place]] = OrderedDict()
        self._cache_size = cache_size

    def _get(self, url, params):
        import requests

        sess = self._session or requests.Session()
        resp = sess.get(
            url, params=params, headers={"User-Agent": _USER_AGENT}, timeout=self._timeout
        )
        resp.raise_for_status()
        return resp.json()

    def _nominatim(self, q: str, limit: int) -> list[Place]:
        data = self._get(
            NOMINATIM_URL,
            {"q": q, "format": "jsonv2", "limit": limit, "addressdetails": 0},
        )
        out: list[Place] = []
        for r in data:
            out.append(
                Place(
                    name=r.get("display_name", q),
                    short_name=r.get("name") or r.get("display_name", q).split(",")[0],
                    lat=float(r["lat"]),
                    lon=float(r["lon"]),
                    bbox=_bbox_from_nominatim(r.get("boundingbox")),
                    kind=r.get("type", ""),
                    category=r.get("category", r.get("class", "")),
                    importance=float(r.get("importance", 0.0) or 0.0),
                    source="nominatim",
                )
            )
        return out

    def _photon(self, q: str, limit: int) -> list[Place]:
        data = self._get(PHOTON_URL, {"q": q, "limit": limit})
        out: list[Place] = []
        for feat in data.get("features", []):
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates")
            if not coords or len(coords) < 2:
                continue
            props = feat.get("properties", {})
            label_parts = [
                props.get("name"),
                props.get("city"),
                props.get("state"),
                props.get("country"),
            ]
            name = ", ".join(p for p in label_parts if p) or q
            out.append(
                Place(
                    name=name,
                    short_name=props.get("name") or name.split(",")[0],
                    lat=float(coords[1]),
                    lon=float(coords[0]),
                    bbox=_bbox_from_photon(props.get("extent")),
                    kind=props.get("osm_value", ""),
                    category=props.get("osm_key", ""),
                    importance=0.0,
                    source="photon",
                )
            )
        return out

    def search(self, q: str, limit: int = 8) -> list[Place]:
        query = (q or "").strip()
        if not query:
            return []
        key = (query.lower(), limit)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        try:
            results = self._nominatim(query, limit)
        except Exception:
            results = []
        if not results:
            try:
                results = self._photon(query, limit)
            except Exception:
                results = []

        self._cache[key] = results
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return results


#: Process-wide default geocoder (Nominatim → Photon, cached).
default_geocoder = Geocoder()
