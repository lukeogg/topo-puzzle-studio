export type Provider =
  | "terrain-tiles"
  | "geotiff"
  | "opentopodata"
  | "usgs-3dep"
  | "opentopography";
export type Assembly = "separate-pieces" | "print-in-place";
export type OutputFormat = "stl" | "combined-stl" | "obj" | "3mf";
export type ConnectorStyle =
  | "rounded-tab"
  | "straight-tab"
  | "organic-tab"
  | "voronoi-tab";
export type RenderMode = "deboss" | "emboss" | "inlay";
export type OverlayClass = "roads" | "trails" | "waterways" | "lakes";

export interface ElevationBand {
  min_m: number;
  name: string;
  hex?: string | null;
}

export interface LandCoverClass {
  code: number;
  name?: string;
  hex?: string | null;
}

export interface Bounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface WaterConfig {
  enabled: boolean;
  threshold_m: number;
}

export interface TrayConfig {
  enabled: boolean;
  split_oversize?: boolean;
}

/** A single geocode search result from GET /api/geocode. */
export interface GeocodeResult {
  name: string;
  lat: number;
  lon: number;
  bbox: Bounds | null;
  /** Concise label (e.g. "Denver"); may be empty on older backends. */
  short_name?: string;
  /** Feature type: city, peak, park, water, … */
  kind?: string;
  /** OSM class: place, natural, boundary, … */
  category?: string;
  /** 0..1 rank used for ordering. */
  importance?: number;
  /** Which upstream provider answered (nominatim | photon). */
  source?: string;
}

/** The full job request body sent to POST /api/jobs. */
export interface JobRequest {
  provider: Provider;
  geotiff_path?: string;
  bounds?: Bounds;
  size_mm: number;
  base_mm: number;
  z_exaggeration: number;
  rows: number;
  cols: number;
  assembly: Assembly;
  gap_mm: number;
  connector?: { style: ConnectorStyle };
  max_grid: number;
  smoothing_sigma: number;
  labels: boolean;
  water: WaterConfig;
  tray?: TrayConfig;
  magnets?: { enabled: boolean; diameter_mm: number; depth_mm: number };
  overlays?: {
    enabled: boolean;
    classes: OverlayClass[];
    render: RenderMode;
    width_scale: number;
    geojson_path?: string | null;
  };
  landcover?: {
    enabled: boolean;
    raster_path?: string | null;
    mapping: LandCoverClass[];
    shell_mm: number;
  };
  bands?: ElevationBand[];
  contour_bands?: boolean;
  formats: string[];
}

export type JobStatus = "queued" | "running" | "done" | "error";

export interface ReportCheck {
  name: string;
  ok: boolean;
  level: "error" | "warning" | "info";
  message: string;
}

export interface JobReport {
  passed: boolean;
  has_errors: boolean;
  checks: ReportCheck[];
}

/** The shape of both the SSE payload and GET /api/jobs/{id}. */
export interface JobState {
  status: JobStatus;
  stage: string;
  progress: number; // 0..1
  warnings: string[];
  report: JobReport | null;
  footprint_mm: [number, number] | null;
  piece_count: number;
  /** Whether a ZIP exists / download is permitted. False when hard validation errors block export. */
  exportable: boolean;
  /** Whether a preview.glb is available for the 3D viewer. */
  has_preview: boolean;
}

/** Local configuration state for the control panel. */
export interface Config {
  place: string;
  lat: number;
  lon: number;
  provider: Provider;
  geotiffPath: string | null;
  geotiffName: string | null;
  bounds: Bounds;
  sizeMm: number;
  aspect: number; // short / long
  layout: "none" | "2x2" | "3x3" | "4x4" | "custom";
  rows: number;
  cols: number;
  assembly: Assembly;
  gapMm: number;
  connectorStyle: ConnectorStyle;
  zExaggeration: number;
  baseMm: number;
  maxGrid: number;
  smoothingOn: boolean;
  smoothingSigma: number;
  labels: boolean;
  waterOn: boolean;
  waterThreshold: number;
  tray: boolean;
  traySplit: boolean;
  // magnets
  magnetsOn: boolean;
  magnetDiameterMm: number;
  magnetDepthMm: number;
  // Tier-2 contour bands
  contourBandsOn: boolean;
  bandsText: string; // one "min_m:name:hex" per line
  // Tier-3 overlays
  overlaysOn: boolean;
  overlayClasses: OverlayClass[];
  overlayRender: RenderMode;
  overlayWidthScale: number;
  overlayGeojsonPath: string | null;
  overlayGeojsonName: string | null;
  // Tier-4 land cover
  landcoverOn: boolean;
  landcoverRasterPath: string | null;
  landcoverRasterName: string | null;
  landcoverMapText: string; // one "code:name:hex" per line
  landcoverShellMm: number;
  formats: {
    stl: boolean; // always on
    combinedStl: boolean;
    obj: boolean;
    threeMf: boolean;
  };
}
