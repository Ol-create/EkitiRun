// E7: Offline-first checkpoint scanner. Owner: Lead.
import type { Metadata, Viewport } from "next";
import ScannerLoader from "@/components/scanner/ScannerLoader";

export const metadata: Metadata = {
  title: "Checkpoint scanner · EkitiRun",
  robots: { index: false },
};

export const viewport: Viewport = {
  themeColor: "#0B6E4F",
  width: "device-width",
  initialScale: 1,
};

export default function Page() {
  return <ScannerLoader />;
}
