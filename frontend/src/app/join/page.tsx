"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { joinLobby, saveCredentials } from "@/lib/api";
import { ArrowIcon } from "@/components/Icons";

export default function JoinPage() {
  const router = useRouter();
  const [pin, setPin] = useState("");
  const [joining, setJoining] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const normalized = pin.replace(/\D/g, "");
    if (normalized.length !== 6) return setError("Enter the six-digit lobby PIN.");
    setJoining(true);
    setError(null);
    try {
      const response = await joinLobby(normalized);
      saveCredentials(response);
      router.push(`/lobby/${response.lobby.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not join this lobby.");
      setJoining(false);
    }
  };

  const onPinChange = (value: string) => {
    const digits = value.replace(/\D/g, "").slice(0, 6);
    setPin(digits.length > 3 ? `${digits.slice(0, 3)} ${digits.slice(3)}` : digits);
    setError(null);
  };

  return (
    <main className="join-page">
      <Link className="wordmark compact" href="/"><span>GRAVITY</span><span>WARS</span></Link>
      <form className="join-form" onSubmit={submit}>
        <span className="eyebrow">Join a table</span>
        <h1>Enter lobby PIN</h1>
        <label htmlFor="pin">Six-digit PIN</label>
        <input id="pin" className="pin-input" value={pin} onChange={(event) => onPinChange(event.target.value)} inputMode="numeric" autoComplete="one-time-code" placeholder="000 000" autoFocus aria-describedby={error ? "join-error" : undefined} />
        {error && <p className="form-error" id="join-error" role="alert">{error}</p>}
        <button className="button button-primary button-large" type="submit" disabled={joining}>{joining ? <><span className="spinner" /> Joining…</> : <>Join Game <ArrowIcon /></>}</button>
      </form>
    </main>
  );
}
