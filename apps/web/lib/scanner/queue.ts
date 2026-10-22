// Recording scans on the phone and uploading them. Owner: Lead (E7).
import type { QueuedScan, RosterEntry, ScanEntry, ScanStatus, ScannerDB } from "./db";
import { bibFromQr, normalizeBib } from "./qr";

export type RecordResult =
  | { kind: "recorded"; scan: QueuedScan }
  | { kind: "repeat"; bib: string; runnerName: string | null; firstScannedAt: string }
  | { kind: "unreadable" };

/** Save one scan locally. Each runner counts once per checkpoint. */
export async function recordScan(
  db: ScannerDB,
  input: { checkpointId: number; raw: string; entry: ScanEntry; now?: Date; clientId?: string },
): Promise<RecordResult> {
  const bib = input.entry === "qr" ? bibFromQr(input.raw) : normalizeBib(input.raw);
  if (!bib) return { kind: "unreadable" };

  const runner = await db.roster.get(bib);
  const runnerName = runner?.fullName ?? null;
  const earlier = await db.scans.where({ checkpointId: input.checkpointId, bib }).first();
  if (earlier) {
    return { kind: "repeat", bib, runnerName, firstScannedAt: earlier.scannedAt };
  }

  const scan: QueuedScan = {
    clientId: input.clientId ?? crypto.randomUUID(),
    checkpointId: input.checkpointId,
    qrToken: input.entry === "qr" ? input.raw.trim() : bib,
    bib,
    runnerName,
    entry: input.entry,
    scannedAt: (input.now ?? new Date()).toISOString(),
    status: "pending",
  };
  await db.scans.add(scan);
  return { kind: "recorded", scan };
}

export interface ScanCounts {
  total: number;
  pending: number;
  synced: number;
  invalid: number;
}

export async function countScans(db: ScannerDB, checkpointId: number): Promise<ScanCounts> {
  const scans = await db.scans.filter((s) => s.checkpointId === checkpointId).toArray();
  const count = (...statuses: ScanStatus[]) => scans.filter((s) => statuses.includes(s.status)).length;
  return {
    total: scans.length,
    pending: count("pending"),
    synced: count("accepted", "duplicate"),
    invalid: count("invalid"),
  };
}

export async function recentScans(db: ScannerDB, checkpointId: number, limit = 8) {
  const scans = await db.scans.filter((s) => s.checkpointId === checkpointId).toArray();
  return scans.sort((a, b) => b.scannedAt.localeCompare(a.scannedAt)).slice(0, limit);
}

export async function replaceRoster(db: ScannerDB, runners: RosterEntry[]): Promise<void> {
  await db.transaction("rw", db.roster, async () => {
    await db.roster.clear();
    await db.roster.bulkAdd(runners);
  });
}

/** Thrown by `send` when the login expired: scans stay queued until the PIN is entered again. */
export class LoginExpiredError extends Error {}

export type SendBatch = (
  scans: Pick<QueuedScan, "clientId" | "qrToken" | "scannedAt" | "entry">[],
) => Promise<{ clientId: string; status: "accepted" | "duplicate" | "invalid" }[]>;

export const BATCH_SIZE = 100;

/**
 * Upload pending scans, oldest first, in batches. Stops quietly on a network
 * error (the next sync retries) and rethrows LoginExpiredError.
 * Returns how many scans the server answered for.
 */
export async function syncPending(
  db: ScannerDB,
  checkpointId: number,
  send: SendBatch,
): Promise<number> {
  let done = 0;
  for (;;) {
    const batch = (await db.scans.where("status").equals("pending").sortBy("scannedAt"))
      .filter((s) => s.checkpointId === checkpointId)
      .slice(0, BATCH_SIZE);
    if (batch.length === 0) return done;

    let results;
    try {
      results = await send(batch);
    } catch (error) {
      if (error instanceof LoginExpiredError) throw error;
      return done; // offline or server trouble: try again on the next sync
    }
    await db.transaction("rw", db.scans, async () => {
      for (const result of results) {
        await db.scans.update(result.clientId, { status: result.status });
      }
    });
    done += results.length;
    // A partial answer means something is off: stop and retry on the next sync,
    // rather than resending the same scans in a tight loop.
    if (results.length < batch.length) return done;
  }
}
