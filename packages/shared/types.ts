// Shared TypeScript types mirroring the FastAPI contract (packages/mesh config +
// apps/api job payloads). Kept intentionally small; the web app may import these.

export type AssemblyMode = "separate-pieces" | "print-in-place";
export type ExportFormat = "stl" | "combined-stl" | "3mf" | "obj";

// Elevation DEM providers. "opentopography" additionally needs an API key
// (OPENTOPOGRAPHY_API_KEY); the others are keyless.
export type Provider =
  | "geotiff"
  | "terrain-tiles"
  | "opentopodata"
  | "usgs-3dep"
  | "opentopography";

export type ConnectorStyle =
  | "rounded-tab"
  | "straight-tab"
  | "organic-tab"
  | "voronoi-tab"
  | "none";
export type RenderMode = "deboss" | "emboss" | "inlay";
export type OverlayClass = "roads" | "trails" | "waterways" | "lakes";

export interface Bounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface WaterSettings {
  enabled: boolean;
  threshold_m: number;
  recess_mm?: number;
}

export interface ConnectorSettings {
  style?: ConnectorStyle;
  width_frac?: number;
  depth_mm?: number;
  min_wall_mm?: number;
  clearance_mm?: number;
  seed?: number;
}

export interface MagnetSettings {
  enabled: boolean;
  diameter_mm?: number;
  depth_mm?: number;
  margin_mm?: number;
}

export interface TraySettings {
  enabled: boolean;
  wall_mm?: number;
  border_h_mm?: number;
  fit_gap_mm?: number;
  split_oversize?: boolean;
  pin_diameter_mm?: number;
  pin_length_mm?: number;
  pin_clearance_mm?: number;
}

export interface ElevationBand {
  min_m: number;
  name: string;
  hex?: string | null;
}

// Tier-3 OSM overlays. Provide geojson_path (an upload id / path) for the
// offline path, or leave it unset to fetch from Overpass for the bounds.
export interface OverlaySettings {
  enabled: boolean;
  classes?: OverlayClass[];
  render?: RenderMode;
  relief_mm?: number;
  min_width_mm?: number;
  width_scale?: number;
  geojson_path?: string | null;
}

export interface LandCoverClass {
  code: number;
  name?: string;
  hex?: string | null;
}

// Tier-4 land cover. raster_path (upload id / path) selects the offline
// classified-raster path; otherwise ESA WorldCover is fetched for the bounds.
export interface LandCoverSettings {
  enabled: boolean;
  shell_mm?: number;
  min_region_mm2?: number;
  raster_path?: string | null;
  mapping?: LandCoverClass[];
  max_classes?: number;
}

export interface GenerateSettings {
  provider: Provider;
  geotiff_path?: string; // upload_id or absolute path
  bounds?: Bounds; // required for network providers
  place_name?: string;
  size_mm: number; // longest edge
  base_mm: number;
  z_exaggeration: number;
  rows: number;
  cols: number;
  assembly: AssemblyMode;
  gap_mm: number; // print-in-place seam gap
  connector?: ConnectorSettings;
  max_grid: number;
  smoothing_sigma: number;
  water: WaterSettings;
  labels: boolean;
  label_depth_mm?: number;
  tray?: TraySettings;
  magnets?: MagnetSettings;
  overlays?: OverlaySettings;
  landcover?: LandCoverSettings;
  bands?: ElevationBand[];
  contour_bands?: boolean; // Tier-2: emit per-band contour 3MF
  formats: ExportFormat[];
}

export interface Check {
  name: string;
  ok: boolean;
  level: "info" | "warning" | "error";
  message: string;
}

export interface ValidationReport {
  passed: boolean;
  has_errors: boolean;
  checks: Check[];
}

export type JobStatus = "queued" | "running" | "done" | "error";

export interface JobState {
  id: string;
  status: JobStatus;
  stage: string;
  progress: number; // 0..1
  error: string | null;
  warnings: string[];
  report: ValidationReport | null;
  footprint_mm: [number, number] | null;
  piece_count: number;
}
