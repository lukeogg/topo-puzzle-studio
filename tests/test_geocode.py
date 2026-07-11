"""Geocoder tests: normalisation, caching, and fallback. No network."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.geocode import Geocoder  # noqa: E402


class _Resp:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("http error")

    def json(self):
        return self._payload


class _Session:
    """Fake session routing by URL to canned payloads; counts calls."""

    def __init__(self, nominatim=None, photon=None, fail_nominatim=False):
        self._nominatim = nominatim or []
        self._photon = photon or {"features": []}
        self._fail_nominatim = fail_nominatim
        self.calls = {"nominatim": 0, "photon": 0}

    def get(self, url, params=None, headers=None, timeout=0):
        if "nominatim" in url:
            self.calls["nominatim"] += 1
            return _Resp(self._nominatim, ok=not self._fail_nominatim)
        self.calls["photon"] += 1
        return _Resp(self._photon)


_NOMINATIM_HIT = [
    {
        "display_name": "Denver, Colorado, United States",
        "name": "Denver",
        "lat": "39.7392",
        "lon": "-104.9903",
        "type": "city",
        "category": "place",
        "importance": 0.85,
        "boundingbox": ["39.61", "39.91", "-105.10", "-104.60"],
    }
]

_PHOTON_HIT = {
    "features": [
        {
            "geometry": {"type": "Point", "coordinates": [-104.9903, 39.7392]},
            "properties": {
                "name": "Denver",
                "state": "Colorado",
                "country": "United States",
                "osm_key": "place",
                "osm_value": "city",
                "extent": [-105.10, 39.91, -104.60, 39.61],
            },
        }
    ]
}


def test_nominatim_result_is_normalised():
    g = Geocoder(session=_Session(nominatim=_NOMINATIM_HIT))
    (hit,) = g.search("denver")
    assert hit.short_name == "Denver"
    assert hit.kind == "city" and hit.category == "place"
    assert hit.source == "nominatim"
    assert hit.importance == 0.85
    assert hit.bbox == {"south": 39.61, "north": 39.91, "west": -105.10, "east": -104.60}


def test_falls_back_to_photon_when_nominatim_empty():
    sess = _Session(nominatim=[], photon=_PHOTON_HIT)
    g = Geocoder(session=sess)
    (hit,) = g.search("denver")
    assert hit.source == "photon"
    assert hit.short_name == "Denver"
    assert sess.calls["nominatim"] == 1 and sess.calls["photon"] == 1


def test_falls_back_to_photon_when_nominatim_errors():
    sess = _Session(fail_nominatim=True, photon=_PHOTON_HIT)
    g = Geocoder(session=sess)
    (hit,) = g.search("denver")
    assert hit.source == "photon"


def test_results_are_cached():
    sess = _Session(nominatim=_NOMINATIM_HIT)
    g = Geocoder(session=sess)
    g.search("denver")
    g.search("Denver")  # case-insensitive cache hit
    assert sess.calls["nominatim"] == 1


def test_blank_query_returns_empty_without_calling():
    sess = _Session(nominatim=_NOMINATIM_HIT)
    g = Geocoder(session=sess)
    assert g.search("   ") == []
    assert sess.calls["nominatim"] == 0


def test_both_providers_failing_returns_empty():
    sess = _Session(fail_nominatim=True, photon={"features": []})
    g = Geocoder(session=sess)
    assert g.search("nowhere") == []
