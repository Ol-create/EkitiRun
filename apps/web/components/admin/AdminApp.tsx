"use client";
// Organiser sign-in and the race-office panel. Owner: Lead (E16, E17).
import { useCallback, useEffect, useState } from "react";
import {
  listCategories,
  loadAdminSession,
  markDnf,
  recordGunStart,
  signIn,
  signOut,
  undoDnf,
  type AdminSession,
  type Category,
} from "@/lib/admin/client";
import TimeCorrections from "./TimeCorrections";

type Note = { tone: "good" | "bad"; text: string };
const NOTE_STYLE = { good: "bg-green-100 text-green-900", bad: "bg-red-100 text-red-900" };

const lagosTime = (iso: string) =>
  new Date(iso).toLocaleString("en-NG", { timeZone: "Africa/Lagos", dateStyle: "medium", timeStyle: "medium" });

function SignIn({ onSignedIn }: { onSignedIn: (s: AdminSession) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const result = await signIn(email, password);
    setBusy(false);
    if (result.ok) onSignedIn(result.data);
    else {
      setError(result.message);
      setPassword("");
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-4 p-4">
      <h1 className="text-2xl font-bold">Organiser sign-in</h1>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          Email
          <input type="email" required autoComplete="username" value={email}
            onChange={(e) => setEmail(e.target.value)} className="rounded-lg border-2 px-3 py-2" />
        </label>
        <label className="flex flex-col gap-1">
          Password
          <input type="password" required autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} className="rounded-lg border-2 px-3 py-2" />
        </label>
        {error && <p className="rounded bg-red-100 p-2 text-red-900">{error}</p>}
        <button type="submit" disabled={busy} className="rounded-lg bg-gray-900 py-3 font-semibold text-white disabled:opacity-50">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

function RaceOffice({ session, onSignOut }: { session: AdminSession; onSignOut: () => void }) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [note, setNote] = useState<Note | null>(null);
  const [bib, setBib] = useState("");
  const [later, setLater] = useState<Record<number, string>>({});

  const load = useCallback(async () => {
    const result = await listCategories();
    if (result.ok) setCategories(result.data);
  }, []);

  useEffect(() => {
    const first = setTimeout(() => void load(), 0);
    return () => clearTimeout(first);
  }, [load]);

  function report<T>(result: { ok: true; data: T } | { ok: false; message: string; signedOut: boolean }, done: string) {
    if (result.ok) setNote({ tone: "good", text: done });
    else if (result.signedOut) onSignOut();
    else setNote({ tone: "bad", text: result.message });
  }

  async function startNow(c: Category) {
    const again = c.gun_start_at ? ` It already has ${lagosTime(c.gun_start_at)}: this replaces it.` : "";
    if (!window.confirm(`Record the ${c.name} gun start as NOW?${again}`)) return;
    report(await recordGunStart(session, c.id), `${c.name}: gun start recorded.`);
    void load();
  }

  async function setTime(c: Category) {
    const local = later[c.id];
    if (!local) return;
    const iso = new Date(`${local}+01:00`).toISOString(); // typed in Lagos time (WAT)
    if (!window.confirm(`Set the ${c.name} gun start to ${lagosTime(iso)}? All its times are recalculated.`)) return;
    report(await recordGunStart(session, c.id, iso), `${c.name}: gun start set.`);
    void load();
  }

  async function dnf(action: "mark" | "undo") {
    const value = bib.trim().toUpperCase();
    if (!value) return;
    report(
      action === "mark" ? await markDnf(session, value) : await undoDnf(session, value),
      action === "mark" ? `${value} marked DNF.` : `${value} is no longer DNF.`,
    );
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Race office</h1>
          <p className="text-sm text-gray-600">Signed in as {session.admin.name}</p>
        </div>
        <button type="button" onClick={onSignOut} className="rounded-lg border px-3 py-2 text-sm">Sign out</button>
      </header>

      {note && <p role="status" className={`rounded-lg p-3 ${NOTE_STYLE[note.tone]}`}>{note.text}</p>}

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Gun starts</h2>
        <p className="text-sm text-gray-600">Press &ldquo;Start now&rdquo; the moment each race starts. Every elapsed time counts from it.</p>
        {categories.map((c) => (
          <div key={c.id} className="flex flex-col gap-2 rounded-lg border p-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="font-semibold">{c.name}</p>
                <p className={`text-sm ${c.gun_start_at ? "text-green-800" : "text-amber-800"}`}>
                  {c.gun_start_at ? `Started ${lagosTime(c.gun_start_at)}` : "Not started"}
                </p>
              </div>
              <button type="button" onClick={() => void startNow(c)} className="rounded-lg bg-green-700 px-4 py-3 font-semibold text-white">
                Start now
              </button>
            </div>
            <div className="flex gap-2 text-sm">
              <input type="datetime-local" step={1} value={later[c.id] ?? ""} aria-label={`${c.name} gun start (Lagos time)`}
                onChange={(e) => setLater((v) => ({ ...v, [c.id]: e.target.value }))} className="rounded border px-2 py-1" />
              <button type="button" onClick={() => void setTime(c)} className="rounded border px-3">Set time (WAT)</button>
            </div>
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Did not finish</h2>
        <div className="flex gap-2">
          <input value={bib} onChange={(e) => setBib(e.target.value)} placeholder="Bib, e.g. H0042" aria-label="Bib number"
            autoCapitalize="characters" className="min-w-0 flex-1 rounded-lg border-2 px-3 py-2" />
          <button type="button" onClick={() => void dnf("mark")} className="rounded-lg bg-red-700 px-4 font-semibold text-white">Mark DNF</button>
          <button type="button" onClick={() => void dnf("undo")} className="rounded-lg border px-4">Undo</button>
        </div>
      </section>

      <TimeCorrections session={session} onSignOut={onSignOut} />
    </main>
  );
}

export default function AdminApp() {
  const [session, setSession] = useState<AdminSession | null>(() => loadAdminSession());
  if (!session) return <SignIn onSignedIn={setSession} />;
  return (
    <RaceOffice
      session={session}
      onSignOut={() => {
        signOut();
        setSession(null);
      }}
    />
  );
}
