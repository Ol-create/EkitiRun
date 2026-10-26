"use client";
// Loads the kit desk in the browser only: it needs the camera and localStorage.
import dynamic from "next/dynamic";

const KitApp = dynamic(() => import("./KitApp"), {
  ssr: false,
  loading: () => <p className="p-4 text-gray-600">Loading kit desk…</p>,
});

export default function KitLoader() {
  return <KitApp />;
}
