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
  const { config, setBounds, setConfig } = useStore();
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
      // The offline style has nothing to attribute; a real style carries its
      // own provider + OSM credits, which MapLibre reads from style.json.
      attributionControl: styleUrl ? { compact: true } : false,
      dragRotate: false,
    });
    mapRef.current = map;
    const bump = () => setTick((t) => t + 1);
    map.on("move", bump);
    map.on("load", () => {
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
      {!process.env.NEXT_PUBLIC_MAP_STYLE && (
        <div className={styles.offlineBadge}>offline style</div>
      )}
    </div>
  );
}
