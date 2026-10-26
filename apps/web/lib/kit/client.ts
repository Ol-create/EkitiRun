// Kit desk calls to the API, and the desk's login. Owner: Lead (E15).
import { api } from "../api";
import type { components } from "../api-types";
import { deviceId } from "../scanner/session";

export type Assigned = components["schemas"]["KitAssignOut"];
export type Returned = components["schemas"]["KitReturnOut"];
export type Outstanding = components["schemas"]["OutstandingOut"];
export type KitResult<T> =
  | { ok: true; data: T }
  | { ok: false; code: string; message: string; expired: boolean };

export interface KitSession {
  token: string;
  expiresAt: string;
}

const SESSION_KEY = "ekitirun.kit.session";

export function loadKitSession(now = new Date()): KitSession | null {
  try {
    const session = JSON.parse(localStorage.getItem(SESSION_KEY) ?? "null") as KitSession | null;
    return session && new Date(session.expiresAt) > now ? session : null;
  } catch {
    return null;
  }
}

export function clearKitSession() {
  localStorage.removeItem(SESSION_KEY);
}

export async function kitLogin(pin: string): Promise<{ ok: true; session: KitSession } | { ok: false; message: string }> {
  try {
    const { data, error } = await api.POST("/api/v1/kit/login", { body: { pin, device_id: deviceId() } });
    if (!data) return { ok: false, message: error?.detail ?? "Login failed. Try again." };
    const session = { token: data.token, expiresAt: data.expires_at };
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    return { ok: true, session };
  } catch {
    return { ok: false, message: "No connection. The kit desk needs signal." };
  }
}

const auth = (session: KitSession) => ({ headers: { Authorization: `Bearer ${session.token}` } });

async function call<T>(
  request: Promise<{ data?: T; error?: { detail?: string; code?: string }; response: Response }>,
): Promise<KitResult<T>> {
  try {
    const { data, error, response } = await request;
    if (data) return { ok: true, data };
    return {
      ok: false,
      code: error?.code ?? `HTTP_${response.status}`,
      message: error?.detail ?? "Something went wrong. Try again.",
      expired: response.status === 401,
    };
  } catch {
    return { ok: false, code: "OFFLINE", message: "No connection. Check the signal and try again.", expired: false };
  }
}

/** Link a runner (scanned QR, or a typed bib) to a tracker. */
export function assignTracker(session: KitSession, runner: { qr_token: string } | { bib_number: string }, trackerLabel: string) {
  return call<Assigned>(
    api.POST("/api/v1/kit/assign", { ...auth(session), body: { ...runner, tracker_label: trackerLabel } }),
  );
}

export function returnTracker(session: KitSession, trackerLabel: string) {
  return call<Returned>(api.POST("/api/v1/kit/return", { ...auth(session), body: { tracker_label: trackerLabel } }));
}

export function fetchOutstanding(session: KitSession) {
  return call<Outstanding>(api.GET("/api/v1/kit/outstanding", auth(session)));
}
