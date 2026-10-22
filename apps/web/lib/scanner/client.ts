// Scanner calls to the API. Owner: Lead (E7).
import { api } from "../api";
import type { RosterEntry } from "./db";
import { LoginExpiredError, type SendBatch } from "./queue";
import type { ScannerSession } from "./session";

export type LoginResult = { ok: true; session: ScannerSession } | { ok: false; message: string };

export async function login(pin: string, deviceId: string): Promise<LoginResult> {
  try {
    const { data, error } = await api.POST("/api/v1/scanner/login", {
      body: { pin, device_id: deviceId },
    });
    if (data) {
      return { ok: true, session: { token: data.token, expiresAt: data.expires_at, checkpoint: data.checkpoint } };
    }
    return { ok: false, message: error?.detail ?? "Login failed. Try again." };
  } catch {
    return { ok: false, message: "No connection. The first login needs signal." };
  }
}

const auth = (token: string) => ({ headers: { Authorization: `Bearer ${token}` } });

/** Runners on this checkpoint's course, or null if it couldn't be fetched right now. */
export async function fetchRoster(token: string): Promise<RosterEntry[] | null> {
  try {
    const { data, response } = await api.GET("/api/v1/scanner/roster", auth(token));
    if (response.status === 401) throw new LoginExpiredError();
    return data
      ? data.runners.map((r) => ({ bib: r.bib_number, fullName: r.full_name, categoryCode: r.category_code }))
      : null;
  } catch (error) {
    if (error instanceof LoginExpiredError) throw error;
    return null;
  }
}

export function batchSender(session: ScannerSession, deviceId: string): SendBatch {
  return async (scans) => {
    const { data, response } = await api.POST("/api/v1/scans/batch", {
      ...auth(session.token),
      body: {
        device_id: deviceId,
        checkpoint_id: session.checkpoint.id,
        scans: scans.map((s) => ({
          client_id: s.clientId,
          qr_token: s.qrToken,
          scanned_at: s.scannedAt,
          entry: s.entry,
        })),
      },
    });
    if (response.status === 401 || response.status === 403) throw new LoginExpiredError();
    if (!data) throw new Error(`Upload failed (${response.status})`);
    return data.results.map((r) => ({ clientId: r.client_id, status: r.status }));
  };
}
