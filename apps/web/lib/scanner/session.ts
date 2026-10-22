// The scanner's login, kept on the phone. Owner: Lead (E7).
import type { components } from "../api-types";

export type Checkpoint = components["schemas"]["CheckpointInfo"];

export interface ScannerSession {
  token: string;
  expiresAt: string;
  checkpoint: Checkpoint;
}

const SESSION_KEY = "ekitirun.scanner.session";
const DEVICE_KEY = "ekitirun.scanner.deviceId";

/** A random id for this phone, made once. The server uses it to spot clock problems. */
export function deviceId(): string {
  let id = localStorage.getItem(DEVICE_KEY);
  if (!id) {
    id = `phone-${crypto.randomUUID()}`;
    localStorage.setItem(DEVICE_KEY, id);
  }
  return id;
}

export function loadSession(now = new Date()): ScannerSession | null {
  try {
    const session = JSON.parse(localStorage.getItem(SESSION_KEY) ?? "null") as ScannerSession | null;
    return session && new Date(session.expiresAt) > now ? session : null;
  } catch {
    return null;
  }
}

export function saveSession(session: ScannerSession): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}
