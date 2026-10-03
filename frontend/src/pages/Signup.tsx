import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { UserPlus, Sparkles } from "lucide-react";
import { useCopilot } from "@/data/store";
import { t as copy } from "@/i18n";
import { Card, PageHeader, cx } from "@/components/ui";

export default function Signup() {
  const { users, login, lang } = useCopilot();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [userId, setUserIdInput] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError(lang === "bn" ? "পাসওয়ার্ড মিলছে না" : "Passwords do not match");
      return;
    }

    setIsLoading(true);

    setTimeout(() => {
      const id = userId.trim().toUpperCase();
      if (id && users.find((u) => u.user_id === id)) {
        login(id);
        navigate("/");
      } else if (users.length > 0) {
        const userToLogin = users[0];
        login(userToLogin.user_id);
        navigate("/");
      } else {
        setError(lang === "bn" ? "কোনো ব্যবহারকারী পাওয়া যায়নি।" : "No users found.");
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
            title={lang === "bn" ? "সাইন আপ" : "Sign up"}
            subtitle={
              lang === "bn"
                ? "নতুন অ্যাকাউন্ট তৈরি করুন"
                : "Create your account"
            }
          />
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="fullName"
                className="mb-1.5 block text-[12px] font-semibold text-ink-700"
              >
                {lang === "bn" ? "পূর্ণ নাম" : "Full name"}
              </label>
              <input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                placeholder={
                  lang === "bn" ? "আপনার পূর্ণ নাম লিখুন" : "Enter your full name"
                }
                className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-[14px] text-ink-900 shadow-sm transition placeholder:text-ink-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              />
            </div>

            <div>
              <label
                htmlFor="userId"
                className="mb-1.5 block text-[12px] font-semibold text-ink-700"
              >
                {lang === "bn" ? "ব্যবহারকারী আইডি" : "User ID"}
              </label>
              <input
                id="userId"
                type="text"
                value={userId}
                onChange={(e) => setUserIdInput(e.target.value.toUpperCase())}
                placeholder={
                  lang === "bn"
                    ? "যেমন: U00001 (বাধ্যতামূলক নয়)"
                    : "e.g., U00001 (optional)"
                }
                className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-[14px] text-ink-900 shadow-sm transition placeholder:text-ink-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              />
              <p className="mt-1 text-[11px] text-ink-400">
                {lang === "bn"
                  ? "বিদ্যমান অ্যাকাউন্ট ব্যবহার করতে চাইলে U00001 এর মত আইডি লিখুন"
                  : "Use existing ID like U00001 to sign into specific demo account"}
              </p>
            </div>

            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-[12px] font-semibold text-ink-700"
              >
                {lang === "bn" ? "ইমেইল" : "Email"}
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder={
                  lang === "bn" ? "আপনার ইমেইল লিখুন" : "Enter your email"
                }
                className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-[14px] text-ink-900 shadow-sm transition placeholder:text-ink-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              />
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
                  lang === "bn" ? "পাসওয়ার্ড তৈরি করুন" : "Create password"
                }
                className="w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-[14px] text-ink-900 shadow-sm transition placeholder:text-ink-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
              />
            </div>

            <div>
              <label
                htmlFor="confirmPassword"
                className="mb-1.5 block text-[12px] font-semibold text-ink-700"
              >
                {lang === "bn" ? "পাসওয়ার্ড নিশ্চিত করুন" : "Confirm password"}
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                placeholder={
                  lang === "bn"
                    ? "পাসওয়ার্ড পুনরায় লিখুন"
                    : "Re-enter password"
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
              <UserPlus className="h-4 w-4" />
              {isLoading
                ? lang === "bn"
                  ? "সাইন আপ হচ্ছে..."
                  : "Signing up..."
                : lang === "bn"
                  ? "সাইন আপ করুন"
                  : "Sign up"}
            </button>
          </form>

          <div className="mt-4 border-t border-ink-100 pt-4 text-center text-[13px] text-ink-600">
            {lang === "bn" ? "ইতিমধ্যে অ্যাকাউন্ট আছে?" : "Already have an account?"}
            <Link
              to="/login"
              className="ml-1.5 font-semibold text-brand-600 transition hover:text-brand-700"
            >
              {lang === "bn" ? "লগইন করুন" : "Sign in"}
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