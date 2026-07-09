"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
type Rect = { left: number; top: number; width: number; height: number };

/** Fraction of the viewport a freshly-placed selection box spans, per axis. */
const VIEW_BOX_FRAC = 1 / 3;
/** Zoom used for a searched place that carries no bbox to frame. */
const PLACE_ZOOM = 11;
/** Below this, a rubber-band drag is a stray click and is discarded. */
const MIN_DRAW_PX = 12;
/** Gap left around the selection when fitting the camera to it. */
const FIT_PADDING = 70;

/**
 * The selection box a freshly-framed view gets: the middle third of the canvas.
 * Deriving it from screen pixels rather than from the place's ground extent is
 * what guarantees the box is always the same obvious, grabbable size — the
 * ground size falls out of whatever zoom the camera landed on.
 */
function viewportBoxBounds(map: MlMap): Bounds {
  const canvas = map.getCanvas();
  const cx = canvas.clientWidth / 2;
  const cy = canvas.clientHeight / 2;
  const halfW = (canvas.clientWidth * VIEW_BOX_FRAC) / 2;
  const halfH = (canvas.clientHeight * VIEW_BOX_FRAC) / 2;
  const nw = map.unproject([cx - halfW, cy - halfH]);
  const se = map.unproject([cx + halfW, cy + halfH]);
  return {
    west: Math.min(nw.lng, se.lng),
    east: Math.max(nw.lng, se.lng),
    south: Math.min(nw.lat, se.lat),
    north: Math.max(nw.lat, se.lat),
  };
}

/** Screen rect spanned by two canvas-space points, normalized. */
function rectFromPoints(x0: number, y0: number, x1: number, y1: number): Rect {
  return {
    left: Math.min(x0, x1),
    top: Math.min(y0, y1),
    width: Math.abs(x1 - x0),
    height: Math.abs(y1 - y0),
  };
}

export default function MapSelect() {
  const { config, setBounds, setConfig, mapCommand, setMapCommand } = useStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  // Bump to force re-projection of the overlay on every map movement.
  const [, setTick] = useState(0);

  // Armed by the ⬚ button: the next drag anywhere draws a box. Holding Shift
  // does the same thing without the mode. The ref keeps native listeners, which
  // are bound once, from reading a stale value.
  const [drawArmed, setDrawArmed] = useState(false);
  const drawArmedRef = useRef(false);
  drawArmedRef.current = drawArmed;
  // The rubber band, in canvas pixels, while a draw is in flight.
  const [drawRect, setDrawRect] = useState<Rect | null>(null);

  const boundsRef = useRef<Bounds>(config.bounds);
  boundsRef.current = config.bounds;

  // A viewport-sized box placement waiting on the camera to stop moving.
  const pendingSettleRef = useRef<null | (() => void)>(null);

  const applyBounds = useCallback(
    (b: Bounds) => {
      setBounds(b);
      setConfig({ aspect: boundsAspect(b) });
    },
    [setBounds, setConfig]
  );

  const fitToSelection = useCallback(() => {
    const m = mapRef.current;
    if (!m) return;
    const b = boundsRef.current;
    m.fitBounds(
      [
        [b.west, b.south],
        [b.east, b.north],
      ],
      { padding: FIT_PADDING }
    );
  }, []);

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
      // Shift+drag is the draw-a-selection gesture; MapLibre claims it for
      // box-zoom by default.
      boxZoom: false,
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

  // Carry out the store's pending camera instruction. `pan-to` leaves the box
  // alone; `frame-place` replaces it with a fresh viewport-sized one.
  //
  // The command is consumed rather than left standing. This component unmounts
  // whenever the 3D tab takes the pane, so a command left in the store would
  // fire again on remount and silently throw away a box the user had since
  // dragged into place.
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !ready || !mapCommand) return;
    setMapCommand(null);

    if (mapCommand.kind === "pan-to") {
      m.flyTo({ center: mapCommand.center, essential: true });
      return;
    }

    // Supersede a placement still waiting on a previous fly. Tracked in a ref
    // rather than torn down in effect cleanup, because consuming the command
    // above re-runs this effect immediately — cleanup would cancel the very
    // placement we just scheduled.
    if (pendingSettleRef.current) m.off("moveend", pendingSettleRef.current);

    // Registered before the camera moves so it still catches the `moveend` of a
    // fly that MapLibre short-circuits into an instant jump.
    const onSettled = () => {
      pendingSettleRef.current = null;
      applyBounds(viewportBoxBounds(m));
    };
    pendingSettleRef.current = onSettled;
    m.once("moveend", onSettled);

    const { center, bbox } = mapCommand;
    if (bbox) {
      m.fitBounds(
        [
          [bbox.west, bbox.south],
          [bbox.east, bbox.north],
        ],
        { padding: FIT_PADDING, essential: true }
      );
    } else {
      m.flyTo({ center, zoom: PLACE_ZOOM, essential: true });
    }
  }, [mapCommand, ready, applyBounds, setMapCommand]);

  const map = mapRef.current;

  // Project the current bounds to screen pixels for the overlay rectangle.
  let rect: Rect | null = null;
  // Wholly outside the viewport.
  let offscreen = false;
  // Wider or taller than the viewport, so the body blankets the map. Left
  // interactive it would swallow every drag, which reads as the map being dead.
  let oversized = false;
  // No corner handle is on screen, so the box cannot be resized at all. This —
  // not merely being oversized — is what warrants offering a way back to it;
  // zooming into your own selection is normal and must stay quiet.
  let unreachable = false;
  if (map && ready) {
    const b = config.bounds;
    const nw = map.project([b.west, b.north]);
    const se = map.project([b.east, b.south]);
    rect = rectFromPoints(nw.x, nw.y, se.x, se.y);

    const canvas = map.getCanvas();
    const vw = canvas.clientWidth;
    const vh = canvas.clientHeight;
    const { left, top, width, height } = rect;
    oversized = width > vw || height > vh;
    offscreen = left + width < 0 || top + height < 0 || left > vw || top > vh;
    unreachable = ![
      [left, top],
      [left + width, top],
      [left, top + height],
      [left + width, top + height],
    ].some(([x, y]) => x >= 0 && x <= vw && y >= 0 && y <= vh);
  }

  // --- drag handling ---

  /**
   * Rubber-band a brand-new selection out of a bare drag. This is the escape
   * hatch that keeps a box you have panned away from — or one larger than the
   * screen — from stranding the whole UI: you never have to go find the old box
   * to replace it.
   *
   * Panning is suspended for the duration. `pointerdown` fires before the
   * `mousedown` MapLibre pans on, so disabling here is enough to hold the map
   * still without fighting its handlers.
   */
  const beginDraw = useCallback(
    (clientX: number, clientY: number) => {
      const m = mapRef.current;
      if (!m) return;
      const canvasRect = m.getCanvas().getBoundingClientRect();
      const x0 = clientX - canvasRect.left;
      const y0 = clientY - canvasRect.top;
      let cur = rectFromPoints(x0, y0, x0, y0);
      m.dragPan.disable();
      setDrawRect(cur);

      const onMove = (ev: PointerEvent) => {
        cur = rectFromPoints(
          x0,
          y0,
          ev.clientX - canvasRect.left,
          ev.clientY - canvasRect.top
        );
        setDrawRect(cur);
      };
      const finish = (commit: boolean) => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onCancel);
        window.removeEventListener("keydown", onKey);
        // Panning must come back even on a lost pointer-up, or the map is
        // permanently stuck.
        m.dragPan.enable();
        setDrawRect(null);
        // A degenerate drag is a stray click. Keep the old box, and stay armed
        // so a mis-click does not silently drop the mode out from under you.
        if (!commit || cur.width < MIN_DRAW_PX || cur.height < MIN_DRAW_PX) {
          return;
        }
        setDrawArmed(false);
        const a = m.unproject([cur.left, cur.top]);
        const b = m.unproject([cur.left + cur.width, cur.top + cur.height]);
        applyBounds({
          west: Math.min(a.lng, b.lng),
          east: Math.max(a.lng, b.lng),
          south: Math.min(a.lat, b.lat),
          north: Math.max(a.lat, b.lat),
        });
      };
      const onUp = () => finish(true);
      const onCancel = () => finish(false);
      const onKey = (ev: KeyboardEvent) => {
        if (ev.key !== "Escape") return;
        finish(false);
        setDrawArmed(false);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onCancel);
      window.addEventListener("keydown", onKey);
    },
    [applyBounds]
  );

  // Draw-to-create over bare map. Bound natively on the canvas container, which
  // sits under the overlay; drags that start on the box itself are routed into
  // beginDraw by the handlers below.
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !ready) return;
    const el = m.getCanvasContainer();
    const onDown = (e: PointerEvent) => {
      if (e.button !== 0) return;
      if (!e.shiftKey && !drawArmedRef.current) return;
      e.preventDefault();
      e.stopPropagation();
      beginDraw(e.clientX, e.clientY);
    };
    el.addEventListener("pointerdown", onDown);
    return () => el.removeEventListener("pointerdown", onDown);
  }, [ready, beginDraw]);

  // Escape disarms a mode entered by mistake.
  useEffect(() => {
    if (!drawArmed) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawArmed(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawArmed]);

  const dragCorner = (corner: Corner) => (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const m = mapRef.current;
    if (!m) return;
    // Shift, or an armed draw, means "new box" even when the press lands on the
    // old box's furniture.
    if (e.shiftKey || drawArmedRef.current) {
      beginDraw(e.clientX, e.clientY);
      return;
    }
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
    if (e.shiftKey || drawArmedRef.current) {
      beginDraw(e.clientX, e.clientY);
      return;
    }
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
    <div className={`${styles.wrap} ${drawArmed ? styles.drawing : ""}`}>
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
            // An oversized box blankets the canvas; let drags through to the map
            // so panning keeps working. The handles opt back in via CSS.
            pointerEvents: oversized ? "none" : undefined,
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

      {/* Rubber band for an in-flight draw */}
      {drawRect && (
        <div
          className={styles.drawBand}
          style={{
            left: drawRect.left,
            top: drawRect.top,
            width: drawRect.width,
            height: drawRect.height,
          }}
        />
      )}

      <button
        type="button"
        className={`${styles.drawBtn} ${drawArmed ? styles.drawBtnOn : ""}`}
        aria-pressed={drawArmed}
        title="Draw a new selection box — or hold Shift and drag"
        onClick={() => setDrawArmed((v) => !v)}
      >
        ⬚
      </button>

      {/* Recovery: the box exists, but not where you can reach it. */}
      {rect && unreachable && !drawRect && (
        <button
          type="button"
          className={styles.fitChip}
          onClick={fitToSelection}
        >
          {offscreen ? "selection off-screen" : "selection fills view"} · fit
        </button>
      )}

      {/* Hint */}
      <div className={styles.hint}>
        ◂ drag handles resize; shift-drag draws a new box
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
