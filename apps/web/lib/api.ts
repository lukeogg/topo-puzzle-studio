import type {
  ElevationBand,
  GeocodeResult,
  JobRequest,
  JobState,
  LandCoverClass,
} from "./types";

/** Parse a textarea of "min_m:name:hex" lines into elevation bands. */
export function parseBands(text: string): ElevationBand[] {
  const out: ElevationBand[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const [min, name, hex] = line.split(":");
    const min_m = parseFloat(min);
    if (Number.isNaN(min_m) || !name) continue;
    out.push({ min_m, name: name.trim(), hex: hex?.trim() || null });
  }
  return out;
}

/** Parse a textarea of "code:name:hex" lines into a land-cover class mapping. */
export function parseLandCoverMap(text: string): LandCoverClass[] {
  const out: LandCoverClass[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const [code, name, hex] = line.split(":");
    const c = parseInt(code, 10);
    if (Number.isNaN(c)) continue;
    out.push({ code: c, name: name?.trim() || "", hex: hex?.trim() || null });
  }
  return out;
}

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

/**
 * Look up a place name via GET /api/geocode?q=...  Returns an array of results.
 * Resilient by design: any network/parse failure (e.g. the backend is offline)
 * resolves to an empty array so the UI can degrade gracefully.
 *
 * Aborts are the one exception — they rethrow. A superseded search must be
 * distinguishable from "no matches", or the caller would render the stale
 * request's empty array over the newer request's results.
 */
export async function geocode(
  q: string,
  signal?: AbortSignal
): Promise<GeocodeResult[]> {
  const query = q.trim();
  if (!query) return [];
  try {
    const res = await fetch(
      `${API_BASE}/api/geocode?q=${encodeURIComponent(query)}`,
      { signal }
    );
    if (!res.ok) return [];
    const data = await res.json();
    if (!Array.isArray(data)) return [];
    return data as GeocodeResult[];
  } catch (err) {
    if (signal?.aborted || (err as Error)?.name === "AbortError") throw err;
    return [];
  }
}

/** Submit a new generation job. Returns the job id. */
export async function createJob(body: JobRequest): Promise<string> {
  const res = await fetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Job creation failed: ${res.status} ${res.statusText}`);
  }
  const data = (await res.json()) as { job_id: string };
  return data.job_id;
}

/** Upload a file (GeoTIFF DEM, classified raster, or GeoJSON). Returns the upload id. */
export async function uploadFile(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/uploads`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status} ${res.statusText}`);
  }
  const data = (await res.json()) as { upload_id: string };
  return data.upload_id;
}

/** Back-compat alias — the upload endpoint is now generic. */
export const uploadGeotiff = uploadFile;

/** Poll fallback for a job's current state. */
export async function getJob(id: string): Promise<JobState> {
  const res = await fetch(`${API_BASE}/api/jobs/${id}`);
  if (!res.ok) {
    throw new Error(`Job fetch failed: ${res.status}`);
  }
  return (await res.json()) as JobState;
}

export function jobStreamUrl(id: string): string {
  return `${API_BASE}/api/jobs/${id}/stream`;
}

export function previewGlbUrl(id: string): string {
  return `${API_BASE}/api/jobs/${id}/preview.glb`;
}

export function downloadUrl(id: string): string {
  return `${API_BASE}/api/jobs/${id}/download`;
}

/**
 * Subscribe to a job's SSE stream. Calls onUpdate for each payload.
 * Returns an unsubscribe function. Falls back to polling if EventSource
 * errors out repeatedly.
 */
export function subscribeJob(
  id: string,
  onUpdate: (state: JobState) => void,
  onError?: (err: unknown) => void
): () => void {
  let closed = false;
  let poll: ReturnType<typeof setInterval> | null = null;

  const startPolling = () => {
    if (poll || closed) return;
    poll = setInterval(async () => {
      try {
        const state = await getJob(id);
        onUpdate(state);
        if (state.status === "done" || state.status === "error") {
          if (poll) clearInterval(poll);
          poll = null;
        }
      } catch (err) {
        onError?.(err);
      }
    }, 1200);
  };

  let es: EventSource | null = null;
  try {
    es = new EventSource(jobStreamUrl(id));
    es.onmessage = (ev) => {
      try {
        const state = JSON.parse(ev.data) as JobState;
        onUpdate(state);
        if (state.status === "done" || state.status === "error") {
          es?.close();
        }
      } catch (err) {
        onError?.(err);
      }
    };
    es.onerror = (err) => {
      onError?.(err);
      es?.close();
      es = null;
      // Fall back to polling in case the stream is unavailable.
      startPolling();
    };
  } catch (err) {
    onError?.(err);
    startPolling();
  }

  return () => {
    closed = true;
    es?.close();
    if (poll) clearInterval(poll);
  };
}

/** Build the wire-format JobRequest from the local UI config. */
export function buildJobRequest(config: {
  provider: JobRequest["provider"];
  geotiffPath: string | null;
  bounds: JobRequest["bounds"];
  sizeMm: number;
  baseMm: number;
  zExaggeration: number;
  rows: number;
  cols: number;
  assembly: JobRequest["assembly"];
  gapMm: number;
  connectorStyle: NonNullable<JobRequest["connector"]>["style"];
  maxGrid: number;
  smoothingOn: boolean;
  smoothingSigma: number;
  labels: boolean;
  waterOn: boolean;
  waterThreshold: number;
  tray: boolean;
  traySplit: boolean;
  magnetsOn: boolean;
  magnetDiameterMm: number;
  magnetDepthMm: number;
  contourBandsOn: boolean;
  bandsText: string;
  overlaysOn: boolean;
  overlayClasses: NonNullable<JobRequest["overlays"]>["classes"];
  overlayRender: NonNullable<JobRequest["overlays"]>["render"];
  overlayWidthScale: number;
  overlayGeojsonPath: string | null;
  landcoverOn: boolean;
  landcoverRasterPath: string | null;
  landcoverMapText: string;
  landcoverShellMm: number;
  formats: string[];
}): JobRequest {
  const req: JobRequest = {
    provider: config.provider,
    size_mm: config.sizeMm,
    base_mm: config.baseMm,
    z_exaggeration: config.zExaggeration,
    rows: config.rows,
    cols: config.cols,
    assembly: config.assembly,
    gap_mm: config.gapMm,
    connector: { style: config.connectorStyle },
    max_grid: config.maxGrid,
    smoothing_sigma: config.smoothingOn ? config.smoothingSigma : 0,
    labels: config.labels,
    water: { enabled: config.waterOn, threshold_m: config.waterThreshold },
    formats: config.formats,
  };
  // Always send the selected bounds when present — for terrain-tiles the backend
  // fetches that window, and for geotiff it crops the raster to those bounds
  // (falling back to the full raster only when there is no overlap).
  if (config.bounds) {
    req.bounds = config.bounds;
  }
  // The geotiff provider additionally references the uploaded raster.
  if (config.provider === "geotiff" && config.geotiffPath) {
    req.geotiff_path = config.geotiffPath;
  }
  if (config.tray) {
    req.tray = { enabled: true, split_oversize: config.traySplit };
  }
  if (config.magnetsOn) {
    req.magnets = {
      enabled: true,
      diameter_mm: config.magnetDiameterMm,
      depth_mm: config.magnetDepthMm,
    };
  }
  // Tier-2: contour bands need at least one band to slice.
  const bands = parseBands(config.bandsText);
  if (bands.length) req.bands = bands;
  if (config.contourBandsOn && bands.length) req.contour_bands = true;
  // Tier-3: overlays. Without a GeoJSON upload the backend fetches Overpass.
  if (config.overlaysOn && config.overlayClasses.length) {
    req.overlays = {
      enabled: true,
      classes: config.overlayClasses,
      render: config.overlayRender,
      width_scale: config.overlayWidthScale,
      geojson_path: config.overlayGeojsonPath || null,
    };
  }
  // Tier-4: land cover. Without a raster upload the backend fetches WorldCover.
  if (config.landcoverOn) {
    req.landcover = {
      enabled: true,
      raster_path: config.landcoverRasterPath || null,
      mapping: parseLandCoverMap(config.landcoverMapText),
      shell_mm: config.landcoverShellMm,
    };
  }
  return req;
}
