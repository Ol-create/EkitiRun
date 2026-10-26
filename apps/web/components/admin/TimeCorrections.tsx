"use client";
// Race office: add, correct or remove a runner's checkpoint time (E17). Owner: Lead.
// Times are typed and shown in Lagos time (WAT, UTC+1). Every change needs a reason
// and is kept in the history; the original time is never lost.
import { useState } from "react";
import { removeTime, runnerTimes, setTime, type AdminSession, type RunnerTimes } from "@/lib/admin/client";

const WAT_OFFSET_MS = 60 * 60 * 1000;
const SOURCE = { qr: "scanner", manual: "typed on scanner", office: "race office" } as const;

/** ISO time -> "YYYY-MM-DDTHH:mm:ss" in Lagos time, for a datetime-local input. */
const toWatInput = (iso: string) => new Date(Date.parse(iso) + WAT_OFFSET_MS).toISOString().slice(0, 19);
const watLabel = (iso: string) => toWatInput(iso).replace("T", " ");
const hms = (s: number | null | undefined) =>
  s == null ? "" : `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

export default function TimeCorrections({
  session,
  onSignOut,
}: {
  session: AdminSession;
  onSignOut: () => void;
}) {
  const [bib, setBib] = useState("");
  const [runner, setRunner] = useState<RunnerTimes | null>(null);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<{ good: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function load(which = bib) {
    if (!which.trim()) return;
    const result = await runnerTimes(session, which.trim());
    if (result.ok) {
      setRunner(result.data);
      setEdits({});
    } else if (result.signedOut) onSignOut();
    else {
      setRunner(null);
      setMessage({ good: false, text: result.message });
    }
  }

  async function act(change: () => ReturnType<typeof setTime>, done: string) {
    if (reason.trim().length < 5) {
      setMessage({ good: false, text: "Give a reason (at least 5 characters), e.g. \"Finish paper sheet, line 14\"." });
      return;
    }
    setBusy(true);
    const result = await change();
    setBusy(false);
    if (result.ok) {
      setMessage({ good: true, text: done });
      if (runner) await load(runner.bib_number);
    } else if (result.signedOut) onSignOut();
    else setMessage({ good: false, text: result.message });
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">Correct a time</h2>
      <p className="text-sm text-gray-600">
        For paper backup sheets, a scanner phone that died, or a wrong time. Times are in Lagos time (WAT).
        A time entered here wins over phone scans; every change is kept in the history.
      </p>
      <form onSubmit={(e) => { e.preventDefault(); void load(); }} className="flex gap-2">
        <input value={bib} onChange={(e) => setBib(e.target.value)} placeholder="Bib, e.g. H42" aria-label="Bib to correct"
          autoCapitalize="characters" className="min-w-0 flex-1 rounded-lg border-2 px-3 py-2" />
        <button type="submit" className="rounded-lg bg-gray-900 px-4 font-semibold text-white">Look up</button>
      </form>

      {message && (
        <p role="status" className={`rounded-lg p-3 ${message.good ? "bg-green-100 text-green-900" : "bg-red-100 text-red-900"}`}>
          {message.text}
        </p>
      )}

      {runner && (
        <div className="flex flex-col gap-3 rounded-lg border p-3">
          <p className="font-semibold">
            {runner.bib_number} {runner.full_name} · {runner.category_code} · {runner.status}
          </p>
          <label className="flex flex-col gap-1 text-sm">
            Reason (required for every change)
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Finish paper sheet, line 14"
              className="rounded border px-2 py-2" />
          </label>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-600">
                <th className="py-1">Checkpoint</th>
                <th>Time now (WAT)</th>
                <th>Set time (WAT)</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runner.checkpoints.map((cp) => (
                <tr key={cp.checkpoint_id} className="border-t align-top">
                  <td className="py-2 pr-2 font-medium">{cp.checkpoint_name}</td>
                  <td className="py-2 pr-2">
                    {cp.scanned_at ? (
                      <>
                        {watLabel(cp.scanned_at)}
                        <br />
                        <span className="text-gray-600">{hms(cp.elapsed_seconds)} · {cp.entry ? SOURCE[cp.entry] : ""}</span>
                      </>
                    ) : (
                      <span className="text-amber-700">missing</span>
                    )}
                  </td>
                  <td className="py-2 pr-2">
                    <input type="datetime-local" step={1} aria-label={`${cp.checkpoint_name} time (WAT)`}
                      value={edits[cp.checkpoint_id] ?? (cp.scanned_at ? toWatInput(cp.scanned_at) : "")}
                      onChange={(e) => setEdits((v) => ({ ...v, [cp.checkpoint_id]: e.target.value }))}
                      className="rounded border px-1 py-1" />
                  </td>
                  <td className="flex flex-col gap-1 py-2">
                    <button type="button" disabled={busy || !edits[cp.checkpoint_id]}
                      onClick={() => void act(
                        () => setTime(session, runner.bib_number, cp.checkpoint_id, `${edits[cp.checkpoint_id]}+01:00`, reason.trim()),
                        `${runner.bib_number}: ${cp.checkpoint_name} time saved.`,
                      )}
                      className="rounded bg-green-700 px-3 py-1 text-white disabled:opacity-40">Save</button>
                    {cp.scanned_at && (
                      <button type="button" disabled={busy}
                        onClick={() => window.confirm(`Remove ${runner.bib_number}'s time at ${cp.checkpoint_name}?`) && void act(
                          () => removeTime(session, runner.bib_number, cp.checkpoint_id, reason.trim()),
                          `${runner.bib_number}: ${cp.checkpoint_name} time removed.`,
                        )}
                        className="rounded border px-3 py-1">Remove</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {runner.history.length > 0 && (
            <div>
              <h3 className="font-semibold">History</h3>
              <ul className="divide-y text-sm">
                {runner.history.map((h, i) => (
                  <li key={i} className="py-1.5">
                    <strong>{h.action}</strong> {h.checkpoint_name}
                    {h.previous?.corrected_at ? ` from ${watLabel(String(h.previous.corrected_at))}` : ""}
                    {h.new?.corrected_at ? ` to ${watLabel(String(h.new.corrected_at))}` : ""}
                    {" · "}{h.reason}{" · "}{h.admin_name}, {watLabel(h.created_at)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
