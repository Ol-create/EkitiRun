"use client";
// Loads the scanner in the browser only: it needs the camera, localStorage and IndexedDB.
import dynamic from "next/dynamic";

const ScannerApp = dynamic(() => import("./ScannerApp"), {
  ssr: false,
  loading: () => <p className="p-4 text-gray-600">Loading scanner…</p>,
});

export default function ScannerLoader() {
  return <ScannerApp />;
}
