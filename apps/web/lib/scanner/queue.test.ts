import "fake-indexeddb/auto";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ScannerDB } from "./db";
import {
  BATCH_SIZE,
  LoginExpiredError,
  countScans,
  recordScan,
  replaceRoster,
  syncPending,
  type SendBatch,
} from "./queue";

const CP = 7;
const token = (bib: string) => `R1.${bib}.276d64b10f524f92a949d9c29d0d8002.ZNrzLT2Wxvbijz4SRkdA7w`;

let db: ScannerDB;

beforeEach(async () => {
  db = new ScannerDB(`test-${crypto.randomUUID()}`);
  await replaceRoster(db, [{ bib: "H0042", fullName: "Ada Okafor", categoryCode: "HALF" }]);
});

afterEach(async () => {
  await db.delete();
});

describe("recordScan", () => {
  it("queues a QR scan with the runner's name", async () => {
    const result = await recordScan(db, { checkpointId: CP, raw: token("H0042"), entry: "qr" });

    expect(result.kind).toBe("recorded");
    if (result.kind !== "recorded") return;
    expect(result.scan).toMatchObject({
      bib: "H0042",
      runnerName: "Ada Okafor",
      qrToken: token("H0042"),
      status: "pending",
    });
  });

  it("queues a typed bib, sending the bib itself", async () => {
    const result = await recordScan(db, { checkpointId: CP, raw: "h42", entry: "manual" });

    expect(result.kind === "recorded" && result.scan.qrToken).toBe("H0042");
  });

  it("still queues runners missing from the roster (it may be out of date)", async () => {
    const result = await recordScan(db, { checkpointId: CP, raw: token("F0001"), entry: "qr" });

    expect(result.kind === "recorded" && result.scan.runnerName).toBeNull();
  });

  it("counts each runner once per checkpoint", async () => {
    const first = new Date("2027-03-06T07:42:00Z");
    await recordScan(db, { checkpointId: CP, raw: token("H0042"), entry: "qr", now: first });

    const again = await recordScan(db, { checkpointId: CP, raw: "H0042", entry: "manual" });
    const elsewhere = await recordScan(db, { checkpointId: CP + 1, raw: "H0042", entry: "manual" });

    expect(again).toEqual({
      kind: "repeat",
      bib: "H0042",
      runnerName: "Ada Okafor",
      firstScannedAt: first.toISOString(),
    });
    expect(elsewhere.kind).toBe("recorded");
  });

  it("ignores codes that aren't EkitiRun bibs", async () => {
    expect(await recordScan(db, { checkpointId: CP, raw: "WIFI:S:cafe", entry: "qr" })).toEqual({
      kind: "unreadable",
    });
    expect((await countScans(db, CP)).total).toBe(0);
  });
});

describe("syncPending", () => {
  async function queue(n: number) {
    for (let i = 1; i <= n; i++) {
      const bib = `R${String(i).padStart(4, "0")}`;
      await recordScan(db, {
        checkpointId: CP,
        raw: bib,
        entry: "manual",
        now: new Date(Date.UTC(2027, 2, 6, 7, 0, i)),
      });
    }
  }

  const acceptAll: SendBatch = async (scans) =>
    scans.map((s) => ({ clientId: s.clientId, status: "accepted" as const }));

  it("uploads in batches, oldest first, and marks scans synced", async () => {
    await queue(BATCH_SIZE + 5);
    const sizes: number[] = [];
    const firstSent: string[] = [];

    const done = await syncPending(db, CP, async (scans) => {
      sizes.push(scans.length);
      firstSent.push(scans[0].scannedAt);
      return acceptAll(scans);
    });

    expect(done).toBe(BATCH_SIZE + 5);
    expect(sizes).toEqual([BATCH_SIZE, 5]);
    expect(firstSent[0]).toBe("2027-03-06T07:00:01.000Z");
    expect(await countScans(db, CP)).toEqual({ total: 105, pending: 0, synced: 105, invalid: 0 });
  });

  it("keeps scans queued while offline", async () => {
    await queue(3);

    const done = await syncPending(db, CP, async () => {
      throw new TypeError("Failed to fetch");
    });

    expect(done).toBe(0);
    expect((await countScans(db, CP)).pending).toBe(3);
  });

  it("keeps scans queued when the login expired, and says so", async () => {
    await queue(2);

    await expect(
      syncPending(db, CP, async () => {
        throw new LoginExpiredError();
      }),
    ).rejects.toBeInstanceOf(LoginExpiredError);
    expect((await countScans(db, CP)).pending).toBe(2);
  });

  it("records what the server rejected", async () => {
    await queue(2);

    await syncPending(db, CP, async (scans) => [
      { clientId: scans[0].clientId, status: "accepted" },
      { clientId: scans[1].clientId, status: "invalid" },
    ]);

    expect(await countScans(db, CP)).toEqual({ total: 2, pending: 0, synced: 1, invalid: 1 });
  });

  it("stops after a partial answer instead of looping", async () => {
    await queue(3);
    let calls = 0;

    await syncPending(db, CP, async (scans) => {
      calls++;
      return [{ clientId: scans[0].clientId, status: "accepted" }];
    });

    expect(calls).toBe(1);
    expect((await countScans(db, CP)).pending).toBe(2);
  });
});
