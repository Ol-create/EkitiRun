// E16: Organiser sign-in and race-office panel (gun starts, DNF). Owner: Lead.
import type { Metadata } from "next";
import AdminLoader from "@/components/admin/AdminLoader";

export const metadata: Metadata = {
  title: "Race office · EkitiRun",
  robots: { index: false },
};

export default function Page() {
  return <AdminLoader />;
}
