"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { redeemInvitation, saveCredentials } from "@/lib/api";
import { ArrowIcon } from "@/components/Icons";

export default function InvitationPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const enter = async () => {
    const secret = window.location.hash.slice(1);
    if (!secret) return setError("This invitation link is incomplete.");
    setBusy(true); setError(null);
    try {
      const response = await redeemInvitation(secret);
      saveCredentials(response);
      window.history.replaceState({}, "", `/lobby/${response.lobby.id}`);
      router.replace(`/lobby/${response.lobby.id}`);
    } catch (reason) {
      window.history.replaceState({}, "", "/invite");
      setError(reason instanceof Error ? reason.message : "This invitation cannot be used.");
      setBusy(false);
    }
  };
  return <main className="invite-entry-page"><Link className="wordmark compact" href="/"><span>GRAVITY</span><span>WARS</span></Link><section className="invite-entry-card"><div className="invite-ticket" aria-hidden="true"><span /><span /><span /></div><span className="eyebrow">Private invitation</span><h1>You’ve got a seat</h1><p>This link admits one player to one Gravity Wars lobby. It works once.</p>{error && <div className="invite-error" role="alert"><strong>Invitation unavailable</strong><span>{error}</span></div>}{!error && <button className="button button-primary button-large" type="button" disabled={busy} onClick={enter}>{busy ? <><span className="spinner" /> Entering…</> : <>Enter Gravity Wars <ArrowIcon /></>}</button>}</section></main>;
}
