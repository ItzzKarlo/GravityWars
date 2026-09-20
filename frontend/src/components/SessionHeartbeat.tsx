"use client";

import { useEffect } from "react";
import { getAccessSession } from "@/lib/api";

/** A redeemed friend stays authorized while the game is open; unused invites do not renew. */
export default function SessionHeartbeat() {
  useEffect(() => {
    const refresh = () => {
      // The CSRF cookie is a non-secret indicator that this browser has an
      // authenticated session. Never read the HttpOnly authentication cookie.
      if (!document.cookie.split(";").some((part) => part.trim().startsWith("gw_csrf="))) return;
      void getAccessSession().catch(() => undefined);
    };

    const timer = window.setInterval(refresh, 5 * 60 * 1000);
    // A suspended tab may miss intervals; renew promptly upon returning.
    const onVisible = () => { if (!document.hidden) refresh(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return null;
}
