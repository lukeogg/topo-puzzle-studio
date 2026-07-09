"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, {
  type Map as MlMap,
  type StyleSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useStore } from "@/lib/store";
import { boundsMeters, boundsAspect, fmtKm } from "@/lib/geo";
import type { Bounds } from "@/lib/types";
import styles from "./MapSelect.module.css";

/**
 * The same terrarium DEM the mesh pipeline prints from
 * (`providers/terrain_tiles.py`). Rendering it as hillshade means the relief you
 * aim the selection box at is the relief that ends up in the STL, rather than a
 * basemap vendor's independent interpretation of the terrain.
 *
 * Opt-in: this contacts a public tile server, which the offline style promises
 * not to do. Enable with NEXT_PUBLIC_MAP_HILLSHADE=1.
 */
const DEM_TILES =
  "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const DEM_MAXZOOM = 15; // Tilezen/joerd publishes terrarium through z15.
const DEM_ATTRIBUTION =
  'Elevation: <a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md">Tilezen/Mapzen</a> (SRTM, USGS 3DEP, ETOPO1, GMTED2010)';
const DEM_SOURCE = "topo-dem";
const HILLSHADE_LAYER = "topo-hillshade";

const hillshadeEnabled = () =>
  process.env.NEXT_PUBLIC_MAP_HILLSHADE === "1" ||
  process.env.NEXT_PUBLIC_MAP_HILLSHADE === "true";

/**
 * Attach hillshade to whatever style just loaded. Returns a teardown that drops
 * the layer, used to degrade to the bare basemap if the DEM never loads.
 */
function addHillshade(map: MlMap) {
  if (map.getSource(DEM_SOURCE)) return;
  map.addSource(DEM_SOURCE, {
    type: "raster-dem",
    tiles: [DEM_TILES],
    tileSize: 256,
    maxzoom: DEM_MAXZOOM,
    encoding: "terrarium",
    attribution: DEM_ATTRIBUTION,
  });
  // Shading belongs above terrain-ish fills (landcover, water) but beneath the
  // roads and labels drawn over them, otherwise every road picks up the shadow
  // tint. Anchor on the first road-family layer; fall back to the first symbol
  // layer, then to the offline style's graticule.
  const layers = map.getStyle().layers ?? [];
  const before =
    layers.find((l) => /^(road|highway|bridge|tunnel|aeroway)/.test(l.id))?.id ??
    layers.find((l) => l.type === "symbol")?.id ??
    (map.getLayer("graticule") ? "graticule" : undefined);
  map.addLayer(
    {
      id: HILLSHADE_LAYER,
      type: "hillshade",
      source: DEM_SOURCE,
      paint: {
        "hillshade-exaggeration": 0.45,
        "hillshade-shadow-color": "#4a3f2f",
        "hillshade-highlight-color": "#fffaf0",
        "hillshade-accent-color": "#8a7a5f",
      },
    },
    before
  );
}

function removeHillshade(map: MlMap) {
  if (map.getLayer(HILLSHADE_LAYER)) map.removeLayer(HILLSHADE_LAYER);
  if (map.getSource(DEM_SOURCE)) map.removeSource(DEM_SOURCE);
}

/** Build a fully-offline cartographic style: cream background + graticule. */
function offlineStyle(center: [number, number]): StyleSpecification {
  const [lon, lat] = center;
  const span = 1.2; // degrees around center to draw graticule
  const step = 0.05;
  const features: GeoJSON.Feature[] = [];
  for (let x = lon - span; x <= lon + span + 1e-9; x += step) {
    features.push({
      type: "Feature",
      properties: {},
      geometry: {
        type: "LineString",
        coordinates: [
          [x, lat - span],
          [x, lat + span],
        ],
      },
    });
  }
  for (let y = lat - span; y <= lat + span + 1e-9; y += step) {
    features.push({
      type: "Feature",
      properties: {},
      geometry: {
        type: "LineString",
        coordinates: [
          [lon - span, y],
          [lon + span, y],
        ],
      },
    });
  }
  return {
    version: 8,
    // Empty glyphs/sprite are fine; no labels are drawn.
    sources: {
      graticule: {
        type: "geojson",
        data: { type: "FeatureCollection", features },
      },
    },
    layers: [
      {
        id: "bg",
        type: "background",
        paint: { "background-color": "#ece3d1" },
      },
      {
        id: "graticule",
        type: "line",
        source: "graticule",
        paint: {
          "line-color": "#cdbfa6",
          "line-width": 1,
          "line-opacity": 0.55,
        },
      },
    ],
  };
}

type Corner = "nw" | "ne" | "sw" | "se";

export default function MapSelect() {
  const { config, setBounds, setConfig, flyTo } = useStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  // Bump to force re-projection of the overlay on every map movement.
  const [, setTick] = useState(0);

  const boundsRef = useRef<Bounds>(config.bounds);
  boundsRef.current = config.bounds;

  // Init map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const styleUrl = process.env.NEXT_PUBLIC_MAP_STYLE;
    const hillshade = hillshadeEnabled();
    const b = config.bounds;
    const center: [number, number] = [
      (b.west + b.east) / 2,
      (b.south + b.north) / 2,
    ];
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: styleUrl || offlineStyle(center),
      center,
      zoom: 9,
      // The bare offline style has nothing to attribute. A real style carries
      // its own provider + OSM credits, and hillshade pulls in the DEM's — both
      // of which MapLibre reads off the source/style definitions.
      attributionControl: styleUrl || hillshade ? { compact: true } : false,
      dragRotate: false,
    });
    mapRef.current = map;
    const bump = () => setTick((t) => t + 1);
    map.on("move", bump);

    // A single 404 over ocean is routine, so only tear the layer out if the DEM
    // never produced a usable tile at all (offline, S3 unreachable, blocked).
    let demLoaded = false;
    const onSourceData = (e: maplibregl.MapSourceDataEvent) => {
      if (e.sourceId === DEM_SOURCE && e.isSourceLoaded) demLoaded = true;
    };
    map.on("sourcedata", onSourceData);
    // maplibre-gl does not export ErrorEvent, so narrow sourceId structurally.
    map.on("error", (e) => {
      const sourceId = (e as { sourceId?: string }).sourceId;
      if (sourceId !== DEM_SOURCE || demLoaded) return;
      demLoaded = true; // latch, so we only tear down once
      console.warn("Hillshade DEM unavailable; using basemap only.", e.error);
      removeHillshade(map);
    });

    map.on("load", () => {
      if (hillshade) addHillshade(map);
      map.fitBounds(
        [
          [b.west, b.south],
          [b.east, b.north],
        ],
        { padding: 70, duration: 0 }
      );
      setReady(true);
      bump();
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Recenter the map whenever the store requests a flyTo target (place search
  // pick or a lat/lon edit). The selection overlay follows config.bounds.
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !ready || !flyTo) return;
    m.flyTo({ center: flyTo, essential: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flyTo, ready]);

  const map = mapRef.current;

  // Project the current bounds to screen pixels for the overlay rectangle.
  let rect: { left: number; top: number; width: number; height: number } | null =
    null;
  if (map && ready) {
    const b = config.bounds;
    const nw = map.project([b.west, b.north]);
    const se = map.project([b.east, b.south]);
    rect = {
      left: Math.min(nw.x, se.x),
      top: Math.min(nw.y, se.y),
      width: Math.abs(se.x - nw.x),
      height: Math.abs(se.y - nw.y),
    };
  }

  // --- drag handling ---
  const applyBounds = (b: Bounds) => {
    setBounds(b);
    setConfig({ aspect: boundsAspect(b) });
  };

  const dragCorner = (corner: Corner) => (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const m = mapRef.current;
    if (!m) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    const onMove = (ev: PointerEvent) => {
      const canvasRect = m.getCanvas().getBoundingClientRect();
      const ll = m.unproject([
        ev.clientX - canvasRect.left,
        ev.clientY - canvasRect.top,
      ]);
      const b = { ...boundsRef.current };
      if (corner === "nw" || corner === "sw") b.west = ll.lng;
      else b.east = ll.lng;
      if (corner === "nw" || corner === "ne") b.north = ll.lat;
      else b.south = ll.lat;
      // Normalize so west<east and south<north.
      const nb: Bounds = {
        west: Math.min(b.west, b.east),
        east: Math.max(b.west, b.east),
        south: Math.min(b.south, b.north),
        north: Math.max(b.south, b.north),
      };
      applyBounds(nb);
    };
    const onUp = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      (e.target as HTMLElement).releasePointerCapture?.(ev.pointerId);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const dragBody = (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const m = mapRef.current;
    if (!m) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    const canvasRect = m.getCanvas().getBoundingClientRect();
    const startLL = m.unproject([
      e.clientX - canvasRect.left,
      e.clientY - canvasRect.top,
    ]);
    const start = { ...boundsRef.current };
    const onMove = (ev: PointerEvent) => {
      const ll = m.unproject([
        ev.clientX - canvasRect.left,
        ev.clientY - canvasRect.top,
      ]);
      const dLng = ll.lng - startLL.lng;
      const dLat = ll.lat - startLL.lat;
      applyBounds({
        west: start.west + dLng,
        east: start.east + dLng,
        south: start.south + dLat,
        north: start.north + dLat,
      });
    };
    const onUp = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      (e.target as HTMLElement).releasePointerCapture?.(ev.pointerId);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  const { width: mW, height: mH } = boundsMeters(config.bounds);
  const shortMm = Math.round(config.sizeMm * config.aspect);

  return (
    <div className={styles.wrap}>
      <div ref={containerRef} className={styles.map} />

      {/* Selection rectangle overlay */}
      {rect && (
        <div
          className={styles.selection}
          style={{
            left: rect.left,
            top: rect.top,
            width: rect.width,
            height: rect.height,
          }}
          onPointerDown={dragBody}
        >
          {(["nw", "ne", "sw", "se"] as Corner[]).map((c) => (
            <span
              key={c}
              className={`${styles.handle} ${styles[c]}`}
              onPointerDown={dragCorner(c)}
            />
          ))}
        </div>
      )}

      {/* Hint */}
      <div className={styles.hint}>
        ◂ drag handles resize the box;
        <br />
        readout stays live in km + mm at scale
      </div>

      {/* Readouts */}
      <div className={styles.readout}>
        {fmtKm(Math.max(mW, mH))} × {fmtKm(Math.min(mW, mH))} km
        <br />= {config.sizeMm} × {shortMm} mm at scale
      </div>
      {/* Only truthful when nothing at all is fetched — hillshade hits S3. */}
      {!process.env.NEXT_PUBLIC_MAP_STYLE && !hillshadeEnabled() && (
        <div className={styles.offlineBadge}>offline style</div>
      )}
    </div>
  );
}
