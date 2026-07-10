"use client";

import { useEffect, useRef, useState } from "react";
import { useStore, uploadGeotiff } from "@/lib/store";
import { geocode } from "@/lib/api";
import { boundsFromCenterSize, boundsMeters } from "@/lib/geo";
import type { GeocodeResult } from "@/lib/types";
import { SectionLabel } from "./ui/SectionLabel";
import { Toggle } from "./ui/Toggle";
import styles from "./ControlPanel.module.css";

const LAYOUTS: { key: string; label: string; rows: number; cols: number }[] = [
  { key: "none", label: "none", rows: 1, cols: 1 },
  { key: "2x2", label: "2×2", rows: 2, cols: 2 },
  { key: "3x3", label: "3×3", rows: 3, cols: 3 },
  { key: "4x4", label: "4×4", rows: 4, cols: 4 },
  { key: "custom", label: "custom", rows: 3, cols: 3 },
];

export function ControlPanel() {
  const { config, setConfig, setMapCommand, generate, isRunning, job } =
    useStore();
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // --- place search state ---
  const [query, setQuery] = useState(config.place);
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [noResults, setNoResults] = useState(false);
  const [open, setOpen] = useState(false);
  // Suppress the debounced search that would otherwise fire right after a
  // programmatic query update (picking a result).
  const skipSearch = useRef(false);

  useEffect(() => {
    if (skipSearch.current) {
      skipSearch.current = false;
      return;
    }
    const q = query.trim();
    if (!q) {
      setResults([]);
      setNoResults(false);
      setSearching(false);
      setOpen(false);
      return;
    }
    setSearching(true);
    // Cancel a request that already left the gate: clearTimeout only stops one
    // that has not fired yet. Without the abort, a slow "den" could resolve
    // after "denver" and overwrite the newer results.
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      try {
        const res = await geocode(q, ctrl.signal);
        setResults(res);
        setNoResults(res.length === 0);
        setSearching(false);
        setOpen(true);
      } catch {
        // Superseded by a newer query; the effect that replaced us owns the UI.
      }
    }, 400);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [query]);

  // Hand the camera the place and let MapSelect lay the box down once it knows
  // the zoom it landed on. The bbox only steers the camera here; it never
  // becomes the selection, because geocoder bboxes range from a whole state to
  // a single address and neither is a usable drag target.
  const pickResult = (r: GeocodeResult) => {
    skipSearch.current = true;
    setQuery(r.name);
    // The map replaces this provisional box with a viewport-sized one the moment
    // its camera settles. It still has to be written here: the map is unmounted
    // whenever the 3D tab owns the pane, and Generate must never quietly run on
    // the place we just navigated away from.
    const { width, height } = boundsMeters(config.bounds);
    setConfig({
      place: r.name,
      lat: r.lat,
      lon: r.lon,
      bounds: boundsFromCenterSize(r.lat, r.lon, width, height),
    });
    setMapCommand({ kind: "frame-place", center: [r.lon, r.lat], bbox: r.bbox });
    setOpen(false);
    setResults([]);
    setNoResults(false);
  };

  // A typed lat/lon nudges an existing box rather than replacing it: the user
  // has already chosen a size, and the zoom has not changed. Carry width and
  // height across rather than long-edge + aspect, so a box dragged
  // taller-than-wide is not silently rotated to landscape.
  const recenter = (lat: number, lon: number) => {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    const { width, height } = boundsMeters(config.bounds);
    const bounds = boundsFromCenterSize(lat, lon, width, height);
    setConfig({ lat, lon, bounds });
    setMapCommand({ kind: "pan-to", center: [lon, lat] });
  };

  const shortEdge = Math.round(config.sizeMm * config.aspect);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setConfig({ geotiffName: file.name });
    setUploading(true);
    try {
      const id = await uploadGeotiff(file);
      setConfig({ geotiffPath: id });
    } catch {
      // Keep the file name so the user sees their selection even if the
      // backend isn't running; generation will surface the error.
      setConfig({ geotiffPath: null });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className={styles.panel}>
      <div className={styles.scroll}>
        {/* 1. LOCATION */}
        <section className={styles.section}>
          <SectionLabel label="Location" chip="—bbox" />
          <div className={styles.searchWrap}>
            <span className={styles.searchIcon} aria-hidden>
              ⚲
            </span>
            <input
              className={`field ${styles.search}`}
              placeholder="Search a place…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setConfig({ place: e.target.value });
              }}
              onFocus={() => {
                if (results.length || noResults) setOpen(true);
              }}
              onBlur={() => {
                // Delay so a result click registers before the list closes.
                window.setTimeout(() => setOpen(false), 150);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && results.length) {
                  e.preventDefault();
                  pickResult(results[0]);
                } else if (e.key === "Escape") {
                  setOpen(false);
                }
              }}
            />
            {open && (
              <div className={styles.results}>
                {searching && (
                  <div className={styles.resultsMsg}>searching…</div>
                )}
                {!searching && noResults && (
                  <div className={styles.resultsMsg}>no results</div>
                )}
                {!searching &&
                  results.map((r, i) => (
                    <button
                      type="button"
                      key={`${r.name}-${i}`}
                      className={styles.resultItem}
                      // onMouseDown fires before the input's onBlur, keeping the
                      // list alive long enough to complete the pick.
                      onMouseDown={(e) => {
                        e.preventDefault();
                        pickResult(r);
                      }}
                    >
                      <span className={styles.resultName}>{r.name}</span>
                      <span className={styles.resultCoord}>
                        {r.kind ? (
                          <span className={styles.resultKind}>
                            {r.kind.replace(/_/g, " ")}
                          </span>
                        ) : null}
                        {r.lat.toFixed(3)}, {r.lon.toFixed(3)}
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </div>
          <div className={styles.grid2}>
            <input
              className="field"
              type="number"
              step="0.0001"
              aria-label="latitude"
              value={config.lat}
              onChange={(e) => setConfig({ lat: parseFloat(e.target.value) || 0 })}
              onBlur={(e) => recenter(parseFloat(e.target.value) || 0, config.lon)}
              onKeyDown={(e) => {
                if (e.key === "Enter")
                  recenter(parseFloat(e.currentTarget.value) || 0, config.lon);
              }}
            />
            <input
              className="field"
              type="number"
              step="0.0001"
              aria-label="longitude"
              value={config.lon}
              onChange={(e) => setConfig({ lon: parseFloat(e.target.value) || 0 })}
              onBlur={(e) => recenter(config.lat, parseFloat(e.target.value) || 0)}
              onKeyDown={(e) => {
                if (e.key === "Enter")
                  recenter(config.lat, parseFloat(e.currentTarget.value) || 0);
              }}
            />
          </div>
        </section>

        {/* 2. ELEVATION SOURCE */}
        <section className={styles.section}>
          <SectionLabel label="Elevation Source" chip="—provider" />
          <select
            className="field"
            value={config.provider}
            onChange={(e) =>
              setConfig({ provider: e.target.value as typeof config.provider })
            }
          >
            <option value="terrain-tiles">Terrain Tiles (global)</option>
            <option value="usgs-3dep">USGS 3DEP (US, high-res)</option>
            <option value="opentopodata">OpenTopoData (preview, low-res)</option>
            <option value="geotiff">Local GeoTIFF</option>
          </select>
          {config.provider === "geotiff" && (
            <button
              type="button"
              className={styles.dropzone}
              onClick={() => fileRef.current?.click()}
            >
              <span className={styles.dropIcon} aria-hidden>
                ↥
              </span>{" "}
              {uploading
                ? "uploading…"
                : config.geotiffName
                ? config.geotiffName
                : "or upload local GeoTIFF"}
              <input
                ref={fileRef}
                type="file"
                accept=".tif,.tiff,image/tiff"
                className={styles.hiddenFile}
                onChange={onFile}
              />
            </button>
          )}
        </section>

        {/* 3. PHYSICAL SIZE */}
        <section className={styles.section}>
          <SectionLabel label="Physical Size" chip="—size-mm" />
          <div className={styles.suffixWrap}>
            <input
              className={`field ${styles.suffixInput}`}
              type="number"
              min={20}
              aria-label="longest edge in mm"
              value={config.sizeMm}
              onChange={(e) =>
                setConfig({ sizeMm: parseFloat(e.target.value) || 0 })
              }
            />
            <span className={styles.suffix}>mm</span>
            <span className={styles.inlineHelp}>longest edge</span>
          </div>
          <div className="helper">
            → {config.sizeMm} × {shortEdge} mm · aspect locked 🔒
          </div>
        </section>

        {/* 4. PUZZLE LAYOUT */}
        <section className={styles.section}>
          <SectionLabel label="Puzzle Layout" chip="—rows —cols" />
          <div className={styles.segmented}>
            {LAYOUTS.map((l) => (
              <button
                key={l.key}
                type="button"
                className={`${styles.segBtn} ${
                  config.layout === l.key ? styles.segActive : ""
                }`}
                onClick={() =>
                  setConfig({
                    layout: l.key as typeof config.layout,
                    rows: l.rows,
                    cols: l.cols,
                  })
                }
              >
                {l.label}
              </button>
            ))}
          </div>
          {config.layout === "custom" && (
            <div className={styles.grid2} style={{ marginTop: 8 }}>
              <label className={styles.miniLabel}>
                rows
                <input
                  className="field"
                  type="number"
                  min={1}
                  max={12}
                  value={config.rows}
                  onChange={(e) =>
                    setConfig({ rows: Math.max(1, parseInt(e.target.value) || 1) })
                  }
                />
              </label>
              <label className={styles.miniLabel}>
                cols
                <input
                  className="field"
                  type="number"
                  min={1}
                  max={12}
                  value={config.cols}
                  onChange={(e) =>
                    setConfig({ cols: Math.max(1, parseInt(e.target.value) || 1) })
                  }
                />
              </label>
            </div>
          )}
        </section>

        {/* 5. ASSEMBLY MODE */}
        <section className={styles.section}>
          <SectionLabel label="Assembly Mode" chip="—assembly" />
          <div className={styles.cards}>
            <button
              type="button"
              className={`${styles.card} ${
                config.assembly === "separate-pieces" ? styles.cardActive : ""
              }`}
              onClick={() => setConfig({ assembly: "separate-pieces" })}
            >
              <span className={styles.cardTitle}>Separate pieces</span>
              <span className={styles.cardSub}>standalone STLs</span>
            </button>
            <button
              type="button"
              className={`${styles.card} ${
                config.assembly === "print-in-place" ? styles.cardActive : ""
              }`}
              onClick={() => setConfig({ assembly: "print-in-place" })}
            >
              <span className={styles.cardTitle}>Print-in-place</span>
              <span className={styles.cardSub}>one plate · gaps</span>
            </button>
          </div>
          {config.assembly === "print-in-place" && (
            <div style={{ marginTop: 8 }}>
              <div className={styles.suffixWrap}>
                <input
                  className={`field ${styles.suffixInput}`}
                  type="number"
                  step="0.05"
                  min={0}
                  aria-label="seam gap in mm"
                  value={config.gapMm}
                  onChange={(e) =>
                    setConfig({ gapMm: parseFloat(e.target.value) || 0 })
                  }
                />
                <span className={styles.suffix}>mm</span>
                <span className={styles.inlineHelp}>seam gap</span>
              </div>
              {config.gapMm < 0.3 && (
                <div className={styles.warnLine}>
                  ⚠ gaps &lt; 0.30 mm may fuse together while printing
                </div>
              )}
            </div>
          )}
        </section>

        {/* 6. ELEVATION */}
        <section className={styles.section}>
          <SectionLabel label="Elevation" chip="—z-exaggeration · —base-mm" />
          <div className={styles.sliderRow}>
            <span className={styles.sliderLabel}>Exaggerate</span>
            <input
              type="range"
              min={0.5}
              max={4}
              step={0.1}
              value={config.zExaggeration}
              className={styles.range}
              onChange={(e) =>
                setConfig({ zExaggeration: parseFloat(e.target.value) })
              }
            />
            <span className={styles.sliderValue}>
              {config.zExaggeration.toFixed(1)}×
            </span>
          </div>
          <div className={styles.baseRow}>
            <span className={styles.sliderLabel}>Base</span>
            <div className={styles.suffixWrap} style={{ flex: 1 }}>
              <input
                className={`field ${styles.suffixInput}`}
                type="number"
                step="0.1"
                min={0}
                aria-label="base thickness in mm"
                value={config.baseMm}
                onChange={(e) =>
                  setConfig({ baseMm: parseFloat(e.target.value) || 0 })
                }
              />
              <span className={styles.suffix}>mm</span>
            </div>
          </div>
        </section>

        {/* 7. ADVANCED */}
        <section className={styles.section}>
          <button
            type="button"
            className={styles.accordionHead}
            onClick={() => setAdvancedOpen((v) => !v)}
            aria-expanded={advancedOpen}
          >
            <span className="lbl" style={{ letterSpacing: "0.12em" }}>
              ADVANCED
            </span>
            <span className={styles.chevron}>{advancedOpen ? "▾" : "▸"}</span>
          </button>
          {advancedOpen && (
            <div className={styles.accordionBody}>
              <label className={styles.rowLabel}>
                <span>Mesh resolution</span>
                <select
                  className={`field ${styles.inlineSelect}`}
                  value={config.maxGrid}
                  onChange={(e) =>
                    setConfig({ maxGrid: parseInt(e.target.value) })
                  }
                >
                  <option value={200}>max 200 px</option>
                  <option value={400}>max 400 px</option>
                  <option value={800}>max 800 px</option>
                </select>
              </label>

              <div className={styles.rowLabel}>
                <span>Gaussian smoothing</span>
                <Toggle
                  checked={config.smoothingOn}
                  onChange={(v) => setConfig({ smoothingOn: v })}
                  label="Gaussian smoothing"
                />
              </div>
              {config.smoothingOn && (
                <div className={styles.sliderRow}>
                  <span className={styles.sliderLabel}>sigma</span>
                  <input
                    type="range"
                    min={0}
                    max={4}
                    step={0.1}
                    value={config.smoothingSigma}
                    className={styles.range}
                    onChange={(e) =>
                      setConfig({ smoothingSigma: parseFloat(e.target.value) })
                    }
                  />
                  <span className={styles.sliderValue}>
                    {config.smoothingSigma.toFixed(1)}
                  </span>
                </div>
              )}

              <div className={styles.rowLabel}>
                <span>Underside labels</span>
                <Toggle
                  checked={config.labels}
                  onChange={(v) => setConfig({ labels: v })}
                  label="Underside labels"
                />
              </div>

              <div className={styles.rowLabel}>
                <span>Include display tray/frame</span>
                <Toggle
                  checked={config.tray}
                  onChange={(v) => setConfig({ tray: v })}
                  label="Include display tray/frame"
                />
              </div>

              <div className={styles.rowLabel}>
                <span>Water flattening</span>
                <Toggle
                  checked={config.waterOn}
                  onChange={(v) => setConfig({ waterOn: v })}
                  label="Water flattening"
                />
              </div>
              {config.waterOn && (
                <div className={styles.suffixWrap}>
                  <input
                    className={`field ${styles.suffixInput}`}
                    type="number"
                    step="0.5"
                    aria-label="water threshold meters"
                    value={config.waterThreshold}
                    onChange={(e) =>
                      setConfig({
                        waterThreshold: parseFloat(e.target.value) || 0,
                      })
                    }
                  />
                  <span className={styles.suffix}>m</span>
                  <span className={styles.inlineHelp}>threshold</span>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {/* GENERATE */}
      <div className={styles.footer}>
        {isRunning && job && (
          <div className={styles.progressWrap}>
            <div className={styles.progressMeta}>
              <span>{job.stage || job.status}</span>
              <span>{Math.round((job.progress || 0) * 100)}%</span>
            </div>
            <div className={styles.progressTrack}>
              <div
                className={styles.progressBar}
                style={{ width: `${Math.round((job.progress || 0) * 100)}%` }}
              />
            </div>
          </div>
        )}
        <button
          type="button"
          className={styles.generate}
          disabled={isRunning}
          onClick={() => generate()}
        >
          {isRunning ? "GENERATING…" : "GENERATE MODEL →"}
        </button>
      </div>
    </div>
  );
}
