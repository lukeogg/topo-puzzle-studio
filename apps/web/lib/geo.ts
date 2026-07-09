import type { Bounds } from "./types";

const EARTH_M_PER_DEG_LAT = 110574;

export function mPerDegLon(lat: number): number {
  return 111320 * Math.cos((lat * Math.PI) / 180);
}

/** Width/height of a bounds in meters. */
export function boundsMeters(b: Bounds): { width: number; height: number } {
  const midLat = (b.north + b.south) / 2;
  const width = Math.abs(b.east - b.west) * mPerDegLon(midLat);
  const height = Math.abs(b.north - b.south) * EARTH_M_PER_DEG_LAT;
  return { width, height };
}

/** Short/long aspect ratio (<= 1) of the bounds. */
export function boundsAspect(b: Bounds): number {
  const { width, height } = boundsMeters(b);
  const long = Math.max(width, height);
  const short = Math.min(width, height);
  if (long === 0) return 1;
  return short / long;
}

/** Ground metres represented by one printed millimetre along the long edge. */
export function groundMetersPerMm(b: Bounds, sizeMm: number): number {
  const { width, height } = boundsMeters(b);
  const long = Math.max(width, height);
  if (sizeMm === 0) return 0;
  return long / sizeMm;
}

/** Build a bounds rectangle centered on lat/lon with a given long-edge km + aspect. */
export function boundsFromCenter(
  lat: number,
  lon: number,
  longKm: number,
  aspect: number
): Bounds {
  const longM = longKm * 1000;
  const shortM = longM * aspect;
  // Long edge = E-W (width), short edge = N-S (height) by convention here.
  const halfLonDeg = longM / 2 / mPerDegLon(lat);
  const halfLatDeg = shortM / 2 / EARTH_M_PER_DEG_LAT;
  return {
    west: lon - halfLonDeg,
    east: lon + halfLonDeg,
    south: lat - halfLatDeg,
    north: lat + halfLatDeg,
  };
}

export function fmtKm(m: number): string {
  return (m / 1000).toFixed(1);
}
