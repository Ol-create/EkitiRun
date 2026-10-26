"use client";
// Loads the organiser area in the browser only (it keeps the sign-in in sessionStorage).
import dynamic from "next/dynamic";

const AdminApp = dynamic(() => import("./AdminApp"), {
  ssr: false,
  loading: () => <p className="p-4 text-gray-600">Loading…</p>,
});

export default function AdminLoader() {
  return <AdminApp />;
}
