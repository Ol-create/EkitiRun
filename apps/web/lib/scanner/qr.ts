// Reading bibs from QR codes and typed input. Owner: Lead (E7).
// QR tokens look like R1.<bib>.<runner id>.<signature> (see apps/api/app/core/security.py).
// The phone can't check the signature (that needs the server's secret); the server does.

const QR_TOKEN = /^R1\.([A-Z]\d{1,5})\.[0-9a-f]{32}\.[A-Za-z0-9_-]{10,}$/;
const TYPED_BIB = /^([A-Z])\s*0*(\d{1,4})$/;

/** The bib in a scanned EkitiRun QR code, or null if it isn't one. */
export function bibFromQr(raw: string): string | null {
  const match = QR_TOKEN.exec(raw.trim());
  return match ? match[1] : null;
}

/** A typed bib in the official form: "h42", "H 0042" and "H0042" all become "H0042". */
export function normalizeBib(typed: string): string | null {
  const match = TYPED_BIB.exec(typed.trim().toUpperCase());
  return match ? `${match[1]}${match[2].padStart(4, "0")}` : null;
}
