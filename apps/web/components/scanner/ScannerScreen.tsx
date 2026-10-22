"use client";
// The checkpoint scanner itself. Owner: Lead (E7).
//
// Every scan is saved on the phone first (IndexedDB) and uploaded in batches
// every 10 s when there is signal, so scanning never waits for the network.
import { useLiveQuery } from "dexie-react-hooks";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { batchSender, fetchRoster } from "@/lib/scanner/client";
import { ScannerDB, type ScanEntry } from "@/lib/scanner/db";
import { signal } from "@/lib/scanner/feedback";
import {
  LoginExpiredError,
  countScans,
  recentScans,
  recordScan,
  replaceRoster,
  syncPending,
  type RecordResult,
} from "@/lib/scanner/queue";
import { deviceId, type ScannerSession } from "@/lib/scanner/session";
import CameraView from "./CameraView";

const SYNC_EVERY_MS = 10_000;
const ROSTER_EVERY_MS = 10 * 60_000;
const BANNER_MS = 2_000;
const SAME_CODE_IGNORE_MS = 3_000; // the camera sees a held-up QR many times a second

type Banner = { tone: "good" | "warn" | "bad"; title: string; detail: string };

const time = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-NG", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

function bannerFor(result: RecordResult): Banner {
  switch (result.kind) {
    case "recorded":
      return result.scan.runnerName
        ? { tone: "good", title: result.scan.bib, detail: result.scan.runnerName }
        : { tone: "warn", title: result.scan.bib, detail: "Saved, but not on this course's runner list" };
    case "repeat":
      return {
        tone: "warn",
        title: `${result.bib} already scanned`,
        detail: `${result.runnerName ?? "Runner"} at ${time(result.firstScannedAt)}`,
      };
    case "unreadable":
      return { tone: "bad", title: "Not an EkitiRun bib", detail: "Scan the bib's QR code or type the number" };
  }
}

const BANNER_STYLE = {
  good: "bg-green-600 text-white",
  warn: "bg-amber-400 text-gray-900",
  bad: "bg-red-600 text-white",
};

export default function ScannerScreen({
  session,
  onLogout,
}: {
  session: ScannerSession;
  onLogout: () => void;
}) {
  const db = useMemo(() => new ScannerDB(), []);
  const checkpointId = session.checkpoint.id;
  // Live views of the on-phone store: they update by themselves after every scan or upload.
  const counts = useLiveQuery(() => countScans(db, checkpointId), [db, checkpointId]) ?? {
    total: 0,
    pending: 0,
    synced: 0,
    invalid: 0,
  };
  const recent = useLiveQuery(() => recentScans(db, checkpointId), [db, checkpointId]) ?? [];
  const [banner, setBanner] = useState<Banner | null>(null);
  const [online, setOnline] = useState(() => navigator.onLine);
  const [expired, setExpired] = useState(false);
  const [typed, setTyped] = useState("");
  const lastCode = useRef<{ raw: string; at: number } | null>(null);
  const bannerTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncing = useRef(false);

  const sync = useCallback(async () => {
    if (syncing.current || !navigator.onLine) return;
    syncing.current = true;
    try {
      await syncPending(db, checkpointId, batchSender(session, deviceId()));
    } catch (error) {
      if (error instanceof LoginExpiredError) setExpired(true);
    } finally {
      syncing.current = false;
    }
  }, [db, checkpointId, session]);

  const loadRoster = useCallback(async () => {
    try {
      const runners = await fetchRoster(session.token);
      if (runners) await replaceRoster(db, runners);
    } catch (error) {
      if (error instanceof LoginExpiredError) setExpired(true);
    }
  }, [db, session.token]);

  // Runner list and first upload on open, then the timers.
  useEffect(() => {
    const first = setTimeout(() => {
      void loadRoster();
      void sync();
    }, 0);
    const syncTimer = setInterval(() => void sync(), SYNC_EVERY_MS);
    const rosterTimer = setInterval(() => void loadRoster(), ROSTER_EVERY_MS);
    const goOnline = () => {
      setOnline(true);
      void sync();
    };
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      clearTimeout(first);
      clearInterval(syncTimer);
      clearInterval(rosterTimer);
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, [loadRoster, sync]);

  const handle = useCallback(
    async (raw: string, entry: ScanEntry) => {
      const now = Date.now();
      if (entry === "qr" && lastCode.current?.raw === raw && now - lastCode.current.at < SAME_CODE_IGNORE_MS) {
        return;
      }
      lastCode.current = { raw, at: now };

      const result = await recordScan(db, { checkpointId, raw, entry });
      const next = bannerFor(result);
      signal(next.tone === "good");
      setBanner(next);
      if (bannerTimer.current) clearTimeout(bannerTimer.current);
      bannerTimer.current = setTimeout(() => setBanner(null), BANNER_MS);
    },
    [db, checkpointId],
  );

  function submitTyped(event: React.FormEvent) {
    event.preventDefault();
    if (!typed.trim()) return;
    void handle(typed, "manual");
    setTyped("");
  }

  function logout() {
    const warning =
      counts.pending > 0
        ? `${counts.pending} scan(s) are not uploaded yet. They stay on this phone and upload after you log in to this checkpoint again. Log out?`
        : "Log out of this checkpoint?";
    if (window.confirm(warning)) onLogout();
  }

  const cp = session.checkpoint;
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col gap-3 p-3">
      <header className="flex items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">{cp.name}</h1>
          <p className="text-sm text-gray-600">
            {cp.category_codes.join(", ")} · {cp.distance_km} km
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-sm font-semibold ${online ? "text-green-700" : "text-red-700"}`}>
            ● {online ? "Online" : "Offline"}
          </span>
          <button type="button" onClick={logout} className="rounded-lg border px-3 py-2 text-sm">
            Log out
          </button>
        </div>
      </header>

      {expired && (
        <div className="rounded-lg bg-red-100 p-3 text-red-900">
          <p className="font-semibold">Login expired. Scans are safe on this phone.</p>
          <button type="button" onClick={onLogout} className="mt-2 rounded-lg bg-red-700 px-4 py-2 text-white">
            Enter PIN to keep uploading
          </button>
        </div>
      )}

      <CameraView onCode={(raw) => void handle(raw, "qr")} />

      <div
        aria-live="assertive"
        className={`min-h-20 rounded-xl p-3 text-center ${banner ? BANNER_STYLE[banner.tone] : "bg-gray-100 text-gray-500"}`}
      >
        {banner ? (
          <>
            <p className="text-3xl font-bold">{banner.title}</p>
            <p className="text-lg">{banner.detail}</p>
          </>
        ) : (
          <p className="pt-4">Point the camera at a bib</p>
        )}
      </div>

      <form onSubmit={submitTyped} className="flex gap-2">
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder="Type a bib, e.g. H42"
          autoCapitalize="characters"
          autoComplete="off"
          className="min-w-0 flex-1 rounded-lg border-2 px-3 py-3 text-lg"
          aria-label="Bib number"
        />
        <button type="submit" className="rounded-lg bg-gray-900 px-5 text-lg font-semibold text-white">
          Add
        </button>
      </form>

      <dl className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-gray-100 p-2">
          <dt className="text-xs text-gray-600">Scanned</dt>
          <dd className="text-2xl font-bold">{counts.total}</dd>
        </div>
        <div className={`rounded-lg p-2 ${counts.pending ? "bg-amber-100" : "bg-gray-100"}`}>
          <dt className="text-xs text-gray-600">Waiting to upload</dt>
          <dd className="text-2xl font-bold">{counts.pending}</dd>
        </div>
        <div className="rounded-lg bg-gray-100 p-2">
          <dt className="text-xs text-gray-600">Uploaded</dt>
          <dd className="text-2xl font-bold">{counts.synced}</dd>
        </div>
      </dl>
      {counts.invalid > 0 && (
        <p className="rounded-lg bg-red-100 p-2 text-sm text-red-900">
          {counts.invalid} scan(s) were rejected by the server (not a valid bib). Tell the race office.
        </p>
      )}

      <section>
        <h2 className="text-sm font-semibold text-gray-600">Recent scans</h2>
        <ul className="divide-y">
          {recent.map((s) => (
            <li key={s.clientId} className="flex justify-between py-1.5 text-sm">
              <span>
                <strong>{s.bib}</strong> {s.runnerName ?? ""}
                {s.entry === "manual" ? " (typed)" : ""}
              </span>
              <span className="text-gray-600">
                {time(s.scannedAt)} {s.status === "pending" ? "⏳" : s.status === "invalid" ? "✕" : "✓"}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
