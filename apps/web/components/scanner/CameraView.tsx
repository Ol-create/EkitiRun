"use client";
// Camera scanning with html5-qrcode: QR codes, and optionally tracker barcodes (E15). Owner: Lead (E7).
import { useEffect, useRef, useState } from "react";

const READER_ID = "qr-reader";

export default function CameraView({
  onCode,
  barcodes = false,
}: {
  onCode: (raw: string) => void;
  /** Also read 1D barcodes (Code 128 / Code 39 / EAN-13), e.g. tracker labels. */
  barcodes?: boolean;
}) {
  const [problem, setProblem] = useState<string | null>(null);
  const onCodeRef = useRef(onCode);
  useEffect(() => {
    onCodeRef.current = onCode;
  }, [onCode]);

  useEffect(() => {
    let stopped = false;
    let scanner: import("html5-qrcode").Html5Qrcode | null = null;

    (async () => {
      const { Html5Qrcode, Html5QrcodeSupportedFormats } = await import("html5-qrcode");
      if (stopped) return;
      const formats = [Html5QrcodeSupportedFormats.QR_CODE];
      if (barcodes) {
        formats.push(
          Html5QrcodeSupportedFormats.CODE_128,
          Html5QrcodeSupportedFormats.CODE_39,
          Html5QrcodeSupportedFormats.EAN_13,
        );
      }
      scanner = new Html5Qrcode(READER_ID, { verbose: false, formatsToSupport: formats });
      try {
        await scanner.start(
          { facingMode: "environment" },
          { fps: 12, qrbox: barcodes ? { width: 280, height: 160 } : { width: 240, height: 240 } },
          (text) => onCodeRef.current(text),
          () => {}, // "no QR in this frame": normal, ignore
        );
      } catch {
        setProblem("Camera not available. Allow camera access, or type bib numbers below.");
      }
    })();

    return () => {
      stopped = true;
      if (scanner?.isScanning) void scanner.stop().then(() => scanner?.clear());
    };
  }, [barcodes]);

  return (
    <div className="overflow-hidden rounded-xl bg-black">
      <div id={READER_ID} className="w-full" />
      {problem && <p className="bg-amber-100 p-3 text-amber-900">{problem}</p>}
    </div>
  );
}
