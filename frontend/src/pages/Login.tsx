import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LogIn, Sparkles } from "lucide-react";
import { useCopilot } from "@/data/store";
import { t as copy } from "@/i18n";
import { Card, PageHeader, cx } from "@/components/ui";

export default function Login() {
  const { users, login, lang } = useCopilot();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    setTimeout(() => {
      if (users.length > 0) {
        const id = identifier.trim().toUpperCase();
        const match = users.find(
          (u) =>
            u.user_id === id ||
            identifier.toLowerCase().startsWith(u.user_id.toLowerCase()) ||
            identifier.toLowerCase() === u.user_id.toLowerCase(),
        );
        const userToLogin = match || users[0];
        login(userToLogin.user_id);
        navigate("/");
      } else {
        setError(
          lang === "bn" ? "কোনো ব্যবহারকারী পাওয়া যায়নি।" : "No users found.",
        );
      }
      setIsLoading(false);
    }, 300);
  };

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-ink-50 px-4 py-6">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-600 text-[20px] font-black text-white shadow-soft">
            u
          </span>
          <h1 className="mt-4 text-[24px] leading-tight font-bold tracking-[-0.02em] text-ink-900">
            {copy("appName", lang)}
          </h1>
          <p className="mt-1.5 text-[14px] leading-relaxed text-ink-500">
            {copy("appTagline", lang)}
          </p>
        </div>

        <Card className="p-6">
          <PageHeader
            title={lang === "bn" ? "লগইন" : "Sign in"}
            subtitle={
              lang === "bn"
                ? "আপনার অ্যাকাউন্টে প্রবেশ করুন"
                : "Sign in to your account"
            }
          />
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="identifier"
                className="mb-1.5 block text-[12px] font-semibold text-ink-700"
              >
                {lang === "bn" ? "ইউজার আইডি বা ইমেইল" : "User ID or Email"}
              </label>
              <input
                id="identifier"
                type="text"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                required
                placeholder={
                  lang === "bn"
                    ? "যেমন: U00001 অথবা আপনার ইমেইল"
                    : "e.g., U00001 or your email"
                }
                className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-[14px] text-ink-900 shadow-sm transition placeholder:text-ink-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              />
              <p className="mt-1 text-[11px] text-ink-400">
                {lang === "bn"
                  ? "ডেমো অ্যাকাউন্ট: U00001, U00002, U00003..."
                  : "Demo accounts: U00001, U00002, U00003..."}
              </p>
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-[12px] font-semibold text-ink-700"
              >
                {lang === "bn" ? "পাসওয়ার্ড" : "Password"}
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder={
                  lang === "bn" ? "আপনার পাসওয়ার্ড লিখুন" : "Enter your password"
                }
                className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-[14px] text-ink-900 shadow-sm transition placeholder:text-ink-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              />
            </div>

            {error && (
              <div className="rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-[13px] text-brand-700">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className={cx(
                "flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2.5 text-[14px] font-bold text-white transition",
                isLoading
                  ? "cursor-not-allowed opacity-60"
                  : "hover:bg-brand-700",
              )}
            >
              <LogIn className="h-4 w-4" />
              {isLoading
                ? lang === "bn"
                  ? "লগইন হচ্ছে..."
                  : "Signing in..."
                : lang === "bn"
                  ? "লগইন করুন"
                  : "Sign in"}
            </button>
          </form>

          <div className="mt-4 border-t border-ink-100 pt-4 text-center text-[13px] text-ink-600">
            {lang === "bn" ? "অ্যাকাউন্ট নেই?" : "Don't have an account?"}
            <Link
              to="/signup"
              className="ml-1.5 font-semibold text-brand-600 transition hover:text-brand-700"
            >
              {lang === "bn" ? "সাইন আপ করুন" : "Sign up"}
            </Link>
          </div>
        </Card>

        <div className="mt-4 flex items-center justify-center gap-1.5 text-center text-[11px] text-ink-400">
          <Sparkles className="h-3.5 w-3.5" />
          <span>{copy("demoData", lang)}</span>
        </div>
      </div>
    </div>
  );
}