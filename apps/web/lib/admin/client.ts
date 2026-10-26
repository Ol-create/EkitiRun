// Organiser (admin) sign-in and race-office calls. Owner: Lead (E16).
//
// The token is kept in sessionStorage, so closing the tab on a shared race-office
// laptop signs out. Tokens last 12 hours.
import { api } from "../api";
import type { components } from "../api-types";

export type Admin = components["schemas"]["AdminOut"];
export type Category = components["schemas"]["CategoryOut"];
export interface AdminSession {
  token: string;
  expiresAt: string;
  admin: Admin;
}
export type Outcome<T> = { ok: true; data: T } | { ok: false; message: string; signedOut: boolean };

const KEY = "ekitirun.admin.session";

export function loadAdminSession(now = new Date()): AdminSession | null {
  try {
    const session = JSON.parse(sessionStorage.getItem(KEY) ?? "null") as AdminSession | null;
    return session && new Date(session.expiresAt) > now ? session : null;
  } catch {
    return null;
  }
}

export function signOut() {
  sessionStorage.removeItem(KEY);
}

async function outcome<T>(
  request: Promise<{ data?: T; error?: { detail?: string }; response: Response }>,
): Promise<Outcome<T>> {
  try {
    const { data, error, response } = await request;
    if (data !== undefined && response.ok) return { ok: true, data };
    return {
      ok: false,
      message: error?.detail ?? "Something went wrong. Try again.",
      signedOut: response.status === 401,
    };
  } catch {
    return { ok: false, message: "No connection. Check the network and try again.", signedOut: false };
  }
}

export async function signIn(email: string, password: string): Promise<Outcome<AdminSession>> {
  const result = await outcome(api.POST("/api/v1/admin/auth/login", { body: { email, password } }));
  if (!result.ok) return result;
  const session = { token: result.data.token, expiresAt: result.data.expires_at, admin: result.data.admin };
  sessionStorage.setItem(KEY, JSON.stringify(session));
  return { ok: true, data: session };
}

const auth = (s: AdminSession) => ({ headers: { Authorization: `Bearer ${s.token}` } });

export function listCategories() {
  return outcome(api.GET("/api/v1/categories"));
}

/** Record a race's gun start: now, or at `at` (an ISO time) if set afterwards. */
export function recordGunStart(s: AdminSession, categoryId: number, at?: string) {
  return outcome(
    api.POST("/api/v1/admin/categories/{category_id}/gun-start", {
      ...auth(s),
      params: { path: { category_id: categoryId } },
      body: at ? { at } : {},
    }),
  );
}

export function markDnf(s: AdminSession, bib: string) {
  return outcome(
    api.POST("/api/v1/admin/runners/{bib_number}/dnf", { ...auth(s), params: { path: { bib_number: bib } } }),
  );
}

export function undoDnf(s: AdminSession, bib: string) {
  return outcome(
    api.DELETE("/api/v1/admin/runners/{bib_number}/dnf", { ...auth(s), params: { path: { bib_number: bib } } }),
  );
}
