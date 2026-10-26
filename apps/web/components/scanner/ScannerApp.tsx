"use client";
// Scanner entry: PIN login, then the scanner. Browser-only (camera, IndexedDB). Owner: Lead (E7).
import { useEffect, useState } from "react";
import { login } from "@/lib/scanner/client";
import {
  clearSession,
  deviceId,
  loadSession,
  saveSession,
  type ScannerSession,
} from "@/lib/scanner/session";
import PinLogin from "./PinLogin";
import ScannerScreen from "./ScannerScreen";

export default function ScannerApp() {
  const [session, setSession] = useState<ScannerSession | null>(() => loadSession());

  useEffect(() => {
    // The service worker keeps /scanner working in airplane mode, even after a reload.
    // Development builds change constantly, so it only runs in production.
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/scanner-sw.js", { scope: "/scanner" });
    }
  }, []);

  if (!session) {
    return (
      <PinLogin
        title="Checkpoint scanner"
        subtitle="Enter the 6-digit PIN for your checkpoint."
        submitPin={async (pin) => {
          const result = await login(pin, deviceId());
          if (!result.ok) return result;
          saveSession(result.session);
          setSession(result.session);
          return { ok: true };
        }}
      />
    );
  }
  return (
    <ScannerScreen
      key={session.token}
      session={session}
      onLogout={() => {
        clearSession();
        setSession(null);
      }}
    />
  );
}
