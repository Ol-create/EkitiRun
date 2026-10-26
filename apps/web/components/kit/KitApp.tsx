"use client";
// Kit desk entry: PIN, then the desk. Owner: Lead (E15).
import { useState } from "react";
import { clearKitSession, kitLogin, loadKitSession, type KitSession } from "@/lib/kit/client";
import PinLogin from "@/components/scanner/PinLogin";
import KitScreen from "./KitScreen";

export default function KitApp() {
  const [session, setSession] = useState<KitSession | null>(() => loadKitSession());

  if (!session) {
    return (
      <PinLogin
        title="Kit desk"
        subtitle="Enter the kit desk PIN to hand out and take back trackers."
        submitPin={async (pin) => {
          const result = await kitLogin(pin);
          if (!result.ok) return result;
          setSession(result.session);
          return { ok: true };
        }}
      />
    );
  }
  return (
    <KitScreen
      session={session}
      onLogout={() => {
        clearKitSession();
        setSession(null);
      }}
    />
  );
}
