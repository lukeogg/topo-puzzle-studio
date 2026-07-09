"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Bounds, Config, JobState } from "./types";
import {
  buildJobRequest,
  createJob,
  subscribeJob,
  uploadGeotiff,
} from "./api";
import { boundsFromCenter } from "./geo";

const DEFAULT_LAT = 48.62;
const DEFAULT_LON = -111.801;
const DEFAULT_ASPECT = 0.79;

// A default selection rectangle (~22.4 x 17.7 km) around the default center.
const DEFAULT_BOUNDS: Bounds = boundsFromCenter(
  DEFAULT_LAT,
  DEFAULT_LON,
  22.4,
  DEFAULT_ASPECT
);

const DEFAULT_CONFIG: Config = {
  place: "Glacier NP",
  lat: DEFAULT_LAT,
  lon: DEFAULT_LON,
  provider: "terrain-tiles",
  geotiffPath: null,
  geotiffName: null,
  bounds: DEFAULT_BOUNDS,
  sizeMm: 180,
  aspect: DEFAULT_ASPECT,
  layout: "3x3",
  rows: 3,
  cols: 3,
  assembly: "separate-pieces",
  gapMm: 0.4,
  zExaggeration: 1.8,
  baseMm: 3.0,
  maxGrid: 400,
  smoothingOn: false,
  smoothingSigma: 1,
  labels: false,
  waterOn: false,
  waterThreshold: 5,
  formats: { stl: true, combinedStl: false, obj: false, threeMf: true },
};

export type Tab = "map" | "3d";

interface StoreValue {
  config: Config;
  setConfig: (patch: Partial<Config>) => void;
  setBounds: (b: Bounds) => void;

  jobId: string | null;
  job: JobState | null;
  isRunning: boolean;
  hasResult: boolean;
  error: string | null;

  tab: Tab;
  setTab: (t: Tab) => void;
  explode: boolean;
  setExplode: (v: boolean) => void;

  generate: () => Promise<void>;
  reset: () => void;
}

const StoreContext = createContext<StoreValue | null>(null);

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfigState] = useState<Config>(DEFAULT_CONFIG);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<JobState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("map");
  const [explode, setExplode] = useState(false);
  const unsubRef = useRef<null | (() => void)>(null);

  const setConfig = useCallback((patch: Partial<Config>) => {
    setConfigState((prev) => ({ ...prev, ...patch }));
  }, []);

  const setBounds = useCallback((b: Bounds) => {
    setConfigState((prev) => ({ ...prev, bounds: b }));
  }, []);

  const isRunning =
    job != null && (job.status === "queued" || job.status === "running");
  const hasResult = job != null && job.status === "done";

  const reset = useCallback(() => {
    unsubRef.current?.();
    unsubRef.current = null;
    setJob(null);
    setJobId(null);
    setError(null);
    setExplode(false);
    setTab("map");
  }, []);

  const generate = useCallback(async () => {
    setError(null);
    unsubRef.current?.();
    unsubRef.current = null;
    setExplode(false);

    // Optimistic "queued" state so the progress UI shows immediately.
    setJob({
      status: "queued",
      stage: "submitting",
      progress: 0,
      warnings: [],
      report: null,
      footprint_mm: null,
      piece_count: config.rows * config.cols,
    });
    setTab("3d");

    try {
      // The GeoTIFF upload id (if any) is captured in config.geotiffPath by the
      // control panel's file input before generate is invoked.
      const geotiffPath = config.geotiffPath;

      const formats: string[] = ["stl"];
      if (config.formats.combinedStl) formats.push("combined-stl");
      if (config.formats.obj) formats.push("obj");
      if (config.formats.threeMf) formats.push("3mf");

      const body = buildJobRequest({
        provider: config.provider,
        geotiffPath,
        bounds: config.bounds,
        sizeMm: config.sizeMm,
        baseMm: config.baseMm,
        zExaggeration: config.zExaggeration,
        rows: config.rows,
        cols: config.cols,
        assembly: config.assembly,
        gapMm: config.gapMm,
        maxGrid: config.maxGrid,
        smoothingOn: config.smoothingOn,
        smoothingSigma: config.smoothingSigma,
        labels: config.labels,
        waterOn: config.waterOn,
        waterThreshold: config.waterThreshold,
        formats,
      });

      const id = await createJob(body);
      setJobId(id);
      unsubRef.current = subscribeJob(
        id,
        (state) => setJob(state),
        (err) => {
          // Stream errors alone shouldn't blow away an in-progress job; the
          // subscribe helper falls back to polling automatically.
          // eslint-disable-next-line no-console
          console.warn("job stream error", err);
        }
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setJob({
        status: "error",
        stage: "failed to submit",
        progress: 0,
        warnings: [],
        report: null,
        footprint_mm: null,
        piece_count: 0,
      });
    }
  }, [config]);

  const value = useMemo<StoreValue>(
    () => ({
      config,
      setConfig,
      setBounds,
      jobId,
      job,
      isRunning,
      hasResult,
      error,
      tab,
      setTab,
      explode,
      setExplode,
      generate,
      reset,
    }),
    [
      config,
      setConfig,
      setBounds,
      jobId,
      job,
      isRunning,
      hasResult,
      error,
      tab,
      explode,
      generate,
      reset,
    ]
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used within StoreProvider");
  return ctx;
}

export { uploadGeotiff };
