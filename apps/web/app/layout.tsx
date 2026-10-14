import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EkitiRun",
  description: "Registration, live tracking and results for the Ekiti Marathon",
  manifest: "/manifest.webmanifest",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-gray-900">{children}</body>
    </html>
  );
}
