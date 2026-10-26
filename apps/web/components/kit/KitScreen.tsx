"use client";
// Kit collection and tracker returns. Owner: Lead (E15).
//
// Hand out: scan the runner's QR (or type the bib), then the tracker's label.
// Return: scan the tracker's label. The desk only records hand-outs and returns;
// deposit rules are the organisers' call.
import { useCallback, useEffect, useRef, useState } from "react";
import { bibFromQr, normalizeBib } from "@/lib/scanner/qr";
import { signal } from "@/lib/scanner/feedback";
import {
  assignTracker,
  fetchOutstanding,
  returnTracker,
  type KitSession,
  type Outstanding,
} from "@/lib/kit/client";
import CameraView from "@/components/scanner/CameraView";

type Mode = "handout" | "return";
type Runner = { qr_token: string; bib: string } | { bib_number: string; bib: string };
type Banner = { tone: "good" | "warn" | "bad"; title: string; detail: string };

const BANNER_STYLE = {
  good: "bg-green-600 text-white",
  warn: "bg-amber-400 text-gray-900",
  bad: "bg-red-600 text-white",
};
const SAME_CODE_IGNORE_MS = 3_000;
const REFRESH_EVERY_MS = 30_000;

export default function KitScreen({ session, onLogout }: { session: KitSession; onLogout: () => void }) {
  const [mode, setMode] = useState<Mode>("handout");
  const [runner, setRunner] = useState<Runner | null>(null);
  const [banner, setBanner] = useState<Banner | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [outstanding, setOutstanding] = useState<Outstanding | null>(null);
  const [showList, setShowList] = useState(false);
  const lastCode = useRef<{ raw: string; at: number } | null>(null);

  const show = useCallback((next: Banner) => {
    signal(next.tone === "good");
    setBanner(next);
  }, []);

  const refresh = useCallback(async () => {
    const result = await fetchOutstanding(session);
    if (result.ok) setOutstanding(result.data);
    else if (result.expired) onLogout();
  }, [session, onLogout]);

  useEffect(() => {
    const first = setTimeout(() => void refresh(), 0);
    const timer = setInterval(() => void refresh(), REFRESH_EVERY_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [refresh]);

  async function handOut(who: Runner, trackerLabel: string) {
    setBusy(true);
    const body = "qr_token" in who ? { qr_token: who.qr_token } : { bib_number: who.bib_number };
    const result = await assignTracker(session, body, trackerLabel);
    setBusy(false);
    setRunner(null);
    if (result.ok) {
      const a = result.data;
      show({
        tone: a.already_assigned ? "warn" : "good",
        title: `${a.bib_number} → ${a.tracker_label}`,
        detail: a.already_assigned ? `${a.full_name}: already linked, nothing changed` : `${a.full_name} (${a.category_code})`,
      });
      void refresh();
    } else if (result.expired) onLogout();
    else show({ tone: "bad", title: "Not linked", detail: result.message });
  }

  async function takeBack(trackerLabel: string) {
    setBusy(true);
    const result = await returnTracker(session, trackerLabel);
    setBusy(false);
    if (result.ok) {
      show({ tone: "good", title: `${result.data.tracker_label} returned`, detail: `${result.data.bib_number} ${result.data.full_name}` });
      void refresh();
    } else if (result.expired) onLogout();
    else show({ tone: "bad", title: "Not returned", detail: result.message });
  }

  /** A code from the camera or the text box. */
  function handle(raw: string, typedIn: boolean) {
    const text = raw.trim();
    if (!text || busy) return;
    const now = Date.now();
    if (!typedIn && lastCode.current?.raw === text && now - lastCode.current.at < SAME_CODE_IGNORE_MS) return;
    lastCode.current = { raw: text, at: now };

    if (mode === "return") return void takeBack(text);
    if (runner) return void handOut(runner, text);

    const bib = bibFromQr(text);
    if (bib) return setRunner({ qr_token: text, bib });
    if (typedIn) return setRunner({ bib_number: text, bib: normalizeBib(text) ?? text.toUpperCase() });
    show({ tone: "bad", title: "Scan the runner first", detail: "Their bib QR code (or type the bib), then the tracker" });
  }

  function submitTyped(event: React.FormEvent) {
    event.preventDefault();
    handle(typed, true);
    setTyped("");
  }

  const prompt =
    mode === "return"
      ? "Scan the tracker being returned"
      : runner
        ? `Now scan the tracker for ${runner.bib}`
        : "Scan the runner's bib QR code";
  const placeholder = mode === "handout" && !runner ? "Or type the bib, e.g. H42" : "Or type the tracker label, e.g. 31";

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col gap-3 p-3">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Kit desk</h1>
        <button type="button" onClick={onLogout} className="rounded-lg border px-3 py-2 text-sm">
          Log out
        </button>
      </header>

      <div role="tablist" className="grid grid-cols-2 gap-2">
        {(["handout", "return"] as const).map((m) => (
          <button
            key={m}
            role="tab"
            aria-selected={mode === m}
            type="button"
            onClick={() => {
              setMode(m);
              setRunner(null);
              setBanner(null);
            }}
            className={`rounded-lg py-3 font-semibold ${mode === m ? "bg-gray-900 text-white" : "bg-gray-100"}`}
          >
            {m === "handout" ? "Hand out" : "Return"}
          </button>
        ))}
      </div>

      <CameraView barcodes onCode={(raw) => handle(raw, false)} />

      <p className="text-center text-lg font-semibold">{prompt}</p>
      {runner && (
        <button type="button" onClick={() => setRunner(null)} className="text-sm text-gray-600 underline">
          Cancel {runner.bib}
        </button>
      )}

      <div aria-live="assertive" className={`min-h-16 rounded-xl p-3 text-center ${banner ? BANNER_STYLE[banner.tone] : "bg-gray-100 text-gray-500"}`}>
        {banner ? (
          <>
            <p className="text-2xl font-bold">{banner.title}</p>
            <p>{banner.detail}</p>
          </>
        ) : (
          <p className="pt-3">Ready</p>
        )}
      </div>

      <form onSubmit={submitTyped} className="flex gap-2">
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder={placeholder}
          autoCapitalize="characters"
          autoComplete="off"
          className="min-w-0 flex-1 rounded-lg border-2 px-3 py-3 text-lg"
          aria-label={placeholder}
        />
        <button type="submit" disabled={busy} className="rounded-lg bg-gray-900 px-5 text-lg font-semibold text-white disabled:opacity-50">
          OK
        </button>
      </form>

      <section className="rounded-lg bg-gray-100 p-3">
        <button type="button" onClick={() => setShowList((v) => !v)} className="flex w-full justify-between font-semibold">
          <span>Trackers still out: {outstanding?.out ?? "…"}</span>
          <span>{showList ? "Hide" : "Show"}</span>
        </button>
        {showList && outstanding && (
          <ul className="mt-2 divide-y text-sm">
            {outstanding.trackers.map((t) => (
              <li key={t.tracker_label} className="flex justify-between py-1.5">
                <span>
                  <strong>{t.bib_number}</strong> {t.full_name}
                </span>
                <span className={t.race_status === "finished" ? "font-semibold text-amber-700" : "text-gray-600"}>
                  {t.tracker_label} · {t.race_status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
