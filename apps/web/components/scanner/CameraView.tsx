"use client";
// Camera QR scanning with html5-qrcode. Owner: Lead (E7).
import { useEffect, useRef, useState } from "react";

const READER_ID = "qr-reader";

export default function CameraView({ onCode }: { onCode: (raw: string) => void }) {
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
      scanner = new Html5Qrcode(READER_ID, {
        verbose: false,
        formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
      });
      try {
        await scanner.start(
          { facingMode: "environment" },
          { fps: 12, qrbox: { width: 240, height: 240 } },
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
  }, []);

  return (
    <div className="overflow-hidden rounded-xl bg-black">
      <div id={READER_ID} className="w-full" />
      {problem && <p className="bg-amber-100 p-3 text-amber-900">{problem}</p>}
    </div>
  );
}
