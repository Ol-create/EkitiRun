import { describe, expect, it } from "vitest";
import {
  DEFAULT_PACE_S_PER_KM,
  estimatePosition,
  pointAt,
  recentPace,
  type RouteLine,
  type SplitLike,
} from "./tracking";

// A straight 10 km route due north from Ado-Ekiti (1° of latitude ≈ 111.195 km).
const START = [5.2281, 7.6262];
const ROUTE: RouteLine = {
  type: "LineString",
  coordinates: [START, [START[0], START[1] + 10 / 111.195]],
};
const CHECKPOINTS = [0, 5, 8, 10].map((distance_km) => ({ distance_km }));
const T = Date.parse("2027-03-06T07:00:00Z");
const at = (minutes: number) => new Date(T + minutes * 60_000);
const split = (distance_km: number, minutes: number): SplitLike => ({
  distance_km,
  scanned_at: at(minutes).toISOString(),
});

describe("pointAt", () => {
  it("finds points along the route", () => {
    expect(pointAt(ROUTE, 0)).toMatchObject({ lng: START[0], lat: START[1], distance_km: 0 });
    expect(pointAt(ROUTE, 5).lat).toBeCloseTo(START[1] + 5 / 111.195, 4);
  });

  it("stays on the route", () => {
    expect(pointAt(ROUTE, -3).distance_km).toBe(0);
    expect(pointAt(ROUTE, 99).distance_km).toBeCloseTo(10, 2);
  });
});

describe("recentPace", () => {
  it("uses the last two splits", () => {
    // 5 km in 25 min, then 3 km in 18 min: 6:00/km lately
    expect(recentPace([split(0, 0), split(5, 25), split(8, 43)])).toBeCloseTo(360);
  });

  it("falls back without two splits", () => {
    expect(recentPace([split(5, 25)])).toBe(DEFAULT_PACE_S_PER_KM);
    expect(recentPace([])).toBe(DEFAULT_PACE_S_PER_KM);
  });

  it("ignores impossible paces from scanning mistakes", () => {
    expect(recentPace([split(0, 0), split(5, 1)])).toBe(DEFAULT_PACE_S_PER_KM); // 12 s/km
    expect(recentPace([split(0, 0), split(5, 600)])).toBe(DEFAULT_PACE_S_PER_KM); // 2 h/km
  });

  it("accepts splits in any order", () => {
    expect(recentPace([split(5, 25), split(0, 0)])).toBeCloseTo(300);
  });
});

describe("estimatePosition", () => {
  it("moves a runner on from their last checkpoint at their own pace", () => {
    // 5 km in 25 min = 5:00/km; 10 minutes after the 5 km scan they are 2 km further.
    const position = estimatePosition(ROUTE, CHECKPOINTS, [split(0, 0), split(5, 25)], "started", at(35));

    expect(position.is_estimate).toBe(true);
    expect(position.distance_km).toBeCloseTo(7, 5);
    expect(position.lat).toBeCloseTo(START[1] + 7 / 111.195, 4);
  });

  it("never passes the next checkpoint", () => {
    const position = estimatePosition(ROUTE, CHECKPOINTS, [split(0, 0), split(5, 25)], "started", at(120));

    expect(position.distance_km).toBeCloseTo(8, 5);
  });

  it("stays at the last checkpoint if the clock says the scan is in the future", () => {
    const position = estimatePosition(ROUTE, CHECKPOINTS, [split(5, 25)], "started", at(20));

    expect(position.distance_km).toBeCloseTo(5, 5);
  });

  it("uses a given pace", () => {
    const position = estimatePosition(ROUTE, CHECKPOINTS, [split(5, 25)], "started", at(29), 480);

    expect(position.distance_km).toBeCloseTo(5.5, 5);
  });

  it("puts runners who haven't started on the start line", () => {
    expect(estimatePosition(ROUTE, CHECKPOINTS, [], "registered", at(30))).toEqual({
      lat: START[1],
      lng: START[0],
      distance_km: 0,
      is_estimate: false,
    });
  });

  it("puts finishers on the finish line", () => {
    const position = estimatePosition(ROUTE, CHECKPOINTS, [split(10, 50)], "finished", at(90));

    expect(position.is_estimate).toBe(false);
    expect(position.distance_km).toBeCloseTo(10, 2);
  });

  it("leaves DNF runners where they were last seen", () => {
    const position = estimatePosition(ROUTE, CHECKPOINTS, [split(0, 0), split(5, 25)], "dnf", at(90));

    expect(position).toMatchObject({ distance_km: 5, is_estimate: false });
  });
});
