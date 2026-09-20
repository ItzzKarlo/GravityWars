"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { adminLogin } from "@/lib/api";
import { ArrowIcon, LockIcon } from "@/components/Icons";

export default function LoginPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(null);
    try { await adminLogin(password); router.replace("/"); router.refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Sign in failed."); setBusy(false); }
  };
  return <main className="join-page"><Link className="wordmark compact" href="/"><span>GRAVITY</span><span>WARS</span></Link><form className="join-form login-form" onSubmit={submit}><span className="login-lock"><LockIcon /></span><span className="eyebrow">Administrator</span><h1>Open the game room</h1><label htmlFor="password">Password</label><input id="password" className="password-input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" maxLength={256} autoFocus />{error && <p className="form-error" role="alert">{error}</p>}<button className="button button-primary button-large" type="submit" disabled={busy || !password}>{busy ? <><span className="spinner" /> Signing in…</> : <>Sign in <ArrowIcon /></>}</button></form></main>;
}
