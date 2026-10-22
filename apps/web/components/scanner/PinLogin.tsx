"use client";
// Checkpoint PIN keypad. Owner: Lead (E7).
import { useState } from "react";
import { login } from "@/lib/scanner/client";
import { unlockAudio } from "@/lib/scanner/feedback";
import { deviceId, type ScannerSession } from "@/lib/scanner/session";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"];

export default function PinLogin({ onLogin }: { onLogin: (session: ScannerSession) => void }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(full: string) {
    unlockAudio(); // this tap lets the scanner beep later
    setBusy(true);
    setError(null);
    const result = await login(full, deviceId());
    setBusy(false);
    if (result.ok) onLogin(result.session);
    else {
      setError(result.message);
      setPin("");
    }
  }

  function press(key: string) {
    if (busy || !key) return;
    if (key === "⌫") return setPin((p) => p.slice(0, -1));
    const next = (pin + key).slice(0, 6);
    setPin(next);
    if (next.length === 6) void submit(next);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 p-4">
      <div>
        <h1 className="text-2xl font-bold">Checkpoint scanner</h1>
        <p className="text-gray-600">Enter the 6-digit PIN for your checkpoint.</p>
      </div>
      <div aria-live="polite" className="flex justify-center gap-2" aria-label={`${pin.length} of 6 digits`}>
        {Array.from({ length: 6 }, (_, i) => (
          <span
            key={i}
            className={`h-4 w-4 rounded-full border-2 border-gray-800 ${i < pin.length ? "bg-gray-800" : ""}`}
          />
        ))}
      </div>
      {error && <p className="rounded bg-red-100 p-3 text-center font-medium text-red-800">{error}</p>}
      <div className="grid grid-cols-3 gap-3">
        {KEYS.map((key, i) =>
          key ? (
            <button
              key={i}
              type="button"
              disabled={busy}
              onClick={() => press(key)}
              className="h-16 rounded-xl bg-gray-100 text-2xl font-semibold active:bg-gray-300 disabled:opacity-50"
              aria-label={key === "⌫" ? "Delete" : key}
            >
              {key}
            </button>
          ) : (
            <span key={i} />
          ),
        )}
      </div>
      {busy && <p className="text-center text-gray-600">Checking PIN…</p>}
    </main>
  );
}
