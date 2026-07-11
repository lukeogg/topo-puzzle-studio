# Data attribution

Every export includes an `attribution.txt` recording the elevation provider, upstream
source(s), and license. Respect these when you redistribute source data or share
renders publicly. **Generated model geometry is yours** (the tool is MIT licensed);
attribution requirements attach to the *input data*, not your printed object.

## Elevation

- **Local GeoTIFF** — you supply the data; its license is yours to honor.
- **AWS/Mapzen Terrain Tiles** — served from AWS Open Data, courtesy Mapzen/Tilezen.
  Upstream sources include **SRTM**, **USGS 3DEP**, **ETOPO1**, **GMTED2010**, and
  various national datasets. Requirements vary by source and region — see
  <https://github.com/tilezen/joerd/blob/master/docs/attribution.md>.

## Map tiles (UI only)

Whatever tile provider you configure via `NEXT_PUBLIC_MAP_STYLE` carries its own
attribution, which the map UI displays. This is separate from the elevation data.

## Land cover / OSM overlays

- **OpenStreetMap** overlays (Tier 3) require **ODbL** attribution — added to the
  manifest whenever overlays are used.
- **ESA WorldCover** land cover (Tier 4) is **CC BY 4.0** — added to the manifest
  whenever land-cover coloring is used.

The attribution manifest is assembled automatically from the providers actually used
in a given generation.
