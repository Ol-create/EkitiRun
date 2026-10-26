// Where is a runner between checkpoints? Owner: Lead (E10). Frontend 2 calls it; don't change it.
//
// Used on the map when there is no fresh GPS fix (no tracker, flat battery, no signal):
//
//   const position = estimatePosition(route.route, route.checkpoints, runner.splits, runner.status);
//   // recalculate every 10 s while the runner is on course
//
// How it works: take the runner's last checkpoint, then move them along the route at
// their own recent pace for the time since that scan. The estimate never passes the
// next checkpoint, because the runner can't be beyond a checkpoint they haven't been
// scanned at. Finished runners sit on the finish line, runners who haven't started on
// the start line, and DNF runners where they were last seen.
import { along, length, lineString } from "@turf/turf";

export type EstimatedPosition = { lat: number; lng: number; distance_km: number; is_estimate: boolean };

/** A GeoJSON LineString: coordinates are [lng, lat], as GET /api/v1/route returns them. */
export type RouteLine = { type: "LineString"; coordinates: number[][] };
export type CheckpointLike = { distance_km: number };
export type SplitLike = { distance_km: number; scanned_at: string };
export type RunnerStatus = "registered" | "started" | "finished" | "dnf";

/** Used until a runner has two splits to measure their own pace: 6:00 per km. */
export const DEFAULT_PACE_S_PER_KM = 360;
// Paces outside this range are scanning mistakes, not running: ignore them.
const FASTEST_PACE_S_PER_KM = 150; // 2:30/km, faster than the marathon world record
const SLOWEST_PACE_S_PER_KM = 1200; // 20:00/km, a slow walk

/** The point `distanceKm` along the route (clamped to its ends). */
export function pointAt(route: RouteLine, distanceKm: number): { lat: number; lng: number; distance_km: number } {
  const line = lineString(route.coordinates);
  const total = length(line, { units: "kilometers" });
  const km = Math.min(Math.max(distanceKm, 0), total);
  const [lng, lat] = along(line, km, { units: "kilometers" }).geometry.coordinates;
  return { lat, lng, distance_km: km };
}

/** Seconds per km over the runner's last two splits, or `fallback` if that isn't usable. */
export function recentPace(splits: SplitLike[], fallback = DEFAULT_PACE_S_PER_KM): number {
  const ordered = [...splits].sort((a, b) => a.distance_km - b.distance_km);
  if (ordered.length < 2) return fallback;
  const [prev, last] = ordered.slice(-2);
  const km = last.distance_km - prev.distance_km;
  const seconds = (Date.parse(last.scanned_at) - Date.parse(prev.scanned_at)) / 1000;
  const pace = km > 0 ? seconds / km : NaN;
  return pace >= FASTEST_PACE_S_PER_KM && pace <= SLOWEST_PACE_S_PER_KM ? pace : fallback;
}

export function estimatePosition(
  route: RouteLine,
  checkpoints: CheckpointLike[],
  splits: SplitLike[],
  status: RunnerStatus,
  now: Date = new Date(),
  paceSecondsPerKm?: number,
): EstimatedPosition {
  const total = length(lineString(route.coordinates), { units: "kilometers" });
  const last = [...splits].sort((a, b) => a.distance_km - b.distance_km).at(-1);

  if (status === "finished") return { ...pointAt(route, total), is_estimate: false };
  if (!last || status === "registered") return { ...pointAt(route, 0), is_estimate: false };
  if (status === "dnf") return { ...pointAt(route, last.distance_km), is_estimate: false };

  const pace = paceSecondsPerKm ?? recentPace(splits);
  const secondsSince = Math.max(0, (now.getTime() - Date.parse(last.scanned_at)) / 1000);
  const nextCheckpoint = checkpoints
    .map((c) => c.distance_km)
    .filter((km) => km > last.distance_km)
    .sort((a, b) => a - b)[0];
  const limit = Math.min(nextCheckpoint ?? total, total);
  const km = Math.min(last.distance_km + secondsSince / pace, limit);
  return { ...pointAt(route, km), is_estimate: true };
}
