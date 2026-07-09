// Shared TypeScript types mirroring the FastAPI contract (packages/mesh config +
// apps/api job payloads). Kept intentionally small; the web app may import these.

export type AssemblyMode = "separate-pieces" | "print-in-place";
export type ExportFormat = "stl" | "3mf" | "obj";

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

export interface GenerateSettings {
  provider: string; // "geotiff" | "terrain-tiles"
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
  max_grid: number;
  smoothing_sigma: number;
  labels: boolean;
  water: WaterSettings;
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
