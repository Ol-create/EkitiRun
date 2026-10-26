// E15: Kit collection and tracker returns. Owner: Lead.
import type { Metadata, Viewport } from "next";
import KitLoader from "@/components/kit/KitLoader";

export const metadata: Metadata = {
  title: "Kit desk · EkitiRun",
  robots: { index: false },
};

export const viewport: Viewport = { themeColor: "#0B6E4F", width: "device-width", initialScale: 1 };

export default function Page() {
  return <KitLoader />;
}
