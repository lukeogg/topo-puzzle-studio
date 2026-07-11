"""OpenTopography global DEM provider — optional API-key raster source.

Wraps the OpenTopography ``globaldem`` REST API, which returns a GeoTIFF for a
bbox from a chosen global dataset (SRTM, ALOS AW3D30, Copernicus, NASADEM, …).
An API key is required; pass it explicitly or set ``OPENTOPOGRAPHY_API_KEY`` in
the environment.  The public endpoint enforces an area cap, so keep selections
modest.
"""

from __future__ import annotations

import os

from ..config import Bounds
from ..elevation import Attribution
from ._geotiff_bytes import grid_from_geotiff_bytes

GLOBALDEM_URL = "https://portal.opentopography.org/API/globaldem"

# Short human-facing licence notes keyed by demtype.
_DEMTYPE_LICENSE = {
    "SRTMGL1": "NASA SRTM GL1 (30 m) — public domain.",
    "SRTMGL3": "NASA SRTM GL3 (90 m) — public domain.",
    "AW3D30": "JAXA ALOS World 3D 30 m — free use with attribution (JAXA).",
    "COP30": "Copernicus GLO-30 DEM — free use with attribution (ESA).",
    "COP90": "Copernicus GLO-90 DEM — free use with attribution (ESA).",
    "NASADEM": "NASADEM (30 m) — public domain.",
}


class OpenTopographyProvider:
    name = "opentopography"

    def __init__(
        self,
        demtype: str = "SRTMGL1",
        *,
        api_key: str | None = None,
        session=None,
    ):
        self.demtype = demtype
        self.api_key = api_key or os.environ.get("OPENTOPOGRAPHY_API_KEY")
        self._session = session

    def _attribution(self) -> Attribution:
        note = _DEMTYPE_LICENSE.get(self.demtype, "See the dataset's own licence terms.")
        return Attribution(
            provider=f"OpenTopography ({self.demtype})",
            sources=(self.demtype,),
            license=note,
            text=(
                f"Elevation from OpenTopography globaldem dataset '{self.demtype}'. "
                f"{note} Data access provided by the OpenTopography Facility with "
                "support from the U.S. National Science Foundation."
            ),
        )

    def get_elevation_grid(
        self, bounds: Bounds, target_resolution_m: float = 30.0, crs: str = "EPSG:4326"
    ):
        if bounds is None:
            raise ValueError("opentopography provider requires bounds")
        if not self.api_key:
            raise ValueError(
                "opentopography provider requires an API key "
                "(pass api_key= or set OPENTOPOGRAPHY_API_KEY)"
            )
        import requests

        sess = self._session or requests.Session()
        params = {
            "demtype": self.demtype,
            "south": bounds.south,
            "north": bounds.north,
            "west": bounds.west,
            "east": bounds.east,
            "outputFormat": "GTiff",
            "API_Key": self.api_key,
        }
        resp = sess.get(GLOBALDEM_URL, params=params, timeout=60)
        resp.raise_for_status()
        return grid_from_geotiff_bytes(resp.content, self._attribution())
