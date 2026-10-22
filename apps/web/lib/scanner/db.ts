// The scanner's on-phone storage (IndexedDB via Dexie). Owner: Lead (E7).
// Scans are written here first and uploaded later, so nothing is lost without signal.
import Dexie, { type EntityTable } from "dexie";

export type ScanStatus = "pending" | "accepted" | "duplicate" | "invalid";
export type ScanEntry = "qr" | "manual";

export interface QueuedScan {
  clientId: string; // random UUID: a retried upload can never create a second scan
  checkpointId: number;
  qrToken: string; // what the server receives: the QR contents, or the typed bib
  bib: string;
  runnerName: string | null; // from the roster; null if the runner isn't on it
  entry: ScanEntry;
  scannedAt: string; // ISO time from the phone's clock
  status: ScanStatus;
}

export interface RosterEntry {
  bib: string;
  fullName: string;
  categoryCode: string;
}

export class ScannerDB extends Dexie {
  scans!: EntityTable<QueuedScan, "clientId">;
  roster!: EntityTable<RosterEntry, "bib">;

  constructor(name = "ekitirun-scanner") {
    super(name);
    this.version(1).stores({
      scans: "clientId, status, [checkpointId+bib], scannedAt",
      roster: "bib",
    });
  }
}
