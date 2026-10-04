import { useState, type FormEvent } from "react";
import { useAuth } from "@/data/auth";

export default function Auth() {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [userId, setUserId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await signup(email, password, userId || undefined);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to authenticate");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-ink-50 p-6">
      <form onSubmit={submit} className="card w-full max-w-md p-7">
        <div className="mb-6">
          <div className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-brand-600 text-xl font-black text-white">u</div>
          <h1 className="text-2xl font-bold text-ink-900">upay Financial Life Copilot</h1>
          <p className="mt-1 text-sm text-ink-500">{mode === "login" ? "Sign in to your financial workspace." : "Create your secure workspace."}</p>
        </div>
        <label className="mb-4 block text-sm font-semibold text-ink-700">Email<input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2" /></label>
        <label className="mb-4 block text-sm font-semibold text-ink-700">Password<input required minLength={8} type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2" /></label>
        {mode === "signup" ? <label className="mb-4 block text-sm font-semibold text-ink-700">Test user ID (optional)<input value={userId} onChange={(e) => setUserId(e.target.value.toUpperCase())} placeholder="U00001" className="mt-1 w-full rounded-lg border border-ink-200 px-3 py-2" /></label> : null}
        {error ? <p className="mb-4 rounded-lg bg-brand-50 p-3 text-sm text-brand-700">{error}</p> : null}
        <button disabled={busy} className="w-full rounded-lg bg-brand-600 px-4 py-2 font-bold text-white disabled:opacity-50" type="submit">{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
        <button type="button" className="mt-4 w-full text-sm font-semibold text-brand-700" onClick={() => setMode(mode === "login" ? "signup" : "login")}>{mode === "login" ? "Need an account? Sign up" : "Already registered? Sign in"}</button>
      </form>
    </main>
  );
}
