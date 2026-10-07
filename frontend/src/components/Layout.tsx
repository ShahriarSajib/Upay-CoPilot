import { useMemo, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  Activity,
  BadgeCheck,
  BookOpen,
  Bot,
  CalendarClock,
  FlaskConical,
  Gauge,
  HandCoins,
  Landmark,
  Menu,
  Mic,
  PiggyBank,
  Receipt,
  Scale,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Wallet,
  X,
} from "lucide-react";
import { personaLabel } from "@/data/context";
import { useCopilot } from "@/data/store";
import { useAuth } from "@/data/auth";
import { useBundle } from "@/hooks/useBundle";
import { fullDate, taka, toBanglaDigits } from "@/lib/format";
import { t as copy } from "@/i18n";
import { Chip, cx } from "./ui";
import { ConfidenceDot, EvidenceBody } from "./Evidence";
import type { Lang } from "@/types";

interface NavItem {
  to: string;
  key: string;
  icon: typeof Gauge;
}

interface NavGroup {
  key: string;
  items: NavItem[];
}

const NAV: NavGroup[] = [
  {
    key: "groupOverview",
    items: [{ to: "/", key: "dashboard", icon: Gauge }],
  },
  {
    key: "groupUnderstand",
    items: [
      { to: "/health", key: "health", icon: Activity },
      { to: "/spending", key: "spending", icon: TrendingUp },
      { to: "/forecast", key: "forecast", icon: CalendarClock },
      { to: "/cash-out", key: "cashout", icon: HandCoins },
      { to: "/money-sources", key: "sources", icon: Wallet },
    ],
  },
  {
    key: "groupPlan",
    items: [
      { to: "/bills", key: "bills", icon: Receipt },
      { to: "/goals", key: "goals", icon: Target },
      { to: "/simulator", key: "simulator", icon: Sparkles },
      { to: "/emergency-fund", key: "emergency", icon: PiggyBank },
      { to: "/learning", key: "literacy", icon: BookOpen },
      { to: "/review", key: "review", icon: CalendarClock },
    ],
  },
  {
    key: "groupTrust",
    items: [
      { to: "/resilience", key: "resilience", icon: ShieldCheck },
      { to: "/credit-readiness", key: "credit", icon: BadgeCheck },
      { to: "/evaluation", key: "evaluation", icon: Scale },
      { to: "/evidence", key: "evidence", icon: FlaskConical },
    ],
  },
];

const BAND_COLOR: Record<string, string> = {
  strong: "text-mint-700 bg-mint-50 border-mint-100",
  good: "text-mint-700 bg-mint-50 border-mint-100",
  moderate: "text-amber-ink bg-amber-50 border-amber-100",
  weak: "text-brand-700 bg-brand-50 border-brand-200",
  critical: "text-white bg-brand-600 border-brand-600",
};

export default function Layout() {
  const { lang, setLang, banglaNumerals, setBanglaNumerals, users, userId, setUserId, ctx, status, error, evidenceStack, popEvidence, clearEvidence } = useCopilot();
  const { logout } = useAuth();
  const bundle = useBundle();
  const [navOpen, setNavOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const personas = useMemo(() => {
    const map = new Map<string, number>();
    for (const u of users) map.set(u.persona, (map.get(u.persona) ?? 0) + 1);
    return map;
  }, [users]);

  const currentUser = users.find((u) => u.user_id === userId);

  if (status === "error") {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="card max-w-md p-6 text-center">
          <h1 className="text-[18px] font-bold text-ink-900">{copy("loadError", lang)}</h1>
          <p className="mt-2 text-[13px] text-ink-500">{error}</p>
          <code className="mt-3 block rounded-lg bg-ink-50 px-3 py-2 font-mono text-[11px] text-ink-600">
            python scripts/export_frontend_snapshot.py
          </code>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-ink-50">
      {/* Top bar */}
      <header className="no-print sticky top-0 z-40 border-b border-ink-200 bg-white/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-3 px-4">
          <button
            type="button"
            className="rounded-lg p-2 text-ink-600 hover:bg-ink-100 lg:hidden"
            onClick={() => setNavOpen((v) => !v)}
            aria-label="Menu"
          >
            {navOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>

          <NavLink to="/" className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-xl bg-brand-600 text-[15px] font-black text-white">
              u
            </span>
            <span className="hidden sm:block">
              <span className="block text-[14px] leading-tight font-bold tracking-[-0.01em] text-ink-900">
                upay
              </span>
              <span className="block text-[10px] leading-tight font-semibold tracking-wide text-brand-600 uppercase">
                Financial Life Copilot
              </span>
            </span>
          </NavLink>

          <div className="ml-auto flex items-center gap-2">
            {bundle && ctx ? (
              <div className="hidden items-center gap-2 lg:flex">
                <span
                  className={cx(
                    "tabular rounded-lg border px-2.5 py-1 text-[11px] font-bold",
                    BAND_COLOR[bundle.health.band] ?? BAND_COLOR.moderate,
                  )}
                >
                  {bundle.health.score}/100 · {bundle.health.band}
                </span>
                <ConfidenceDot value={bundle.health.evidence.confidence} />
              </div>
            ) : null}

            {/* Language + numerals */}
            <div className="flex items-center rounded-lg border border-ink-200 bg-white p-0.5">
              {(["en", "bn"] as Lang[]).map((l) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => setLang(l)}
                  className={cx(
                    "rounded-md px-2.5 py-1 text-[11px] font-bold transition",
                    lang === l ? "bg-ink-900 text-white" : "text-ink-500 hover:text-ink-800",
                  )}
                  aria-pressed={lang === l}
                >
                  {l === "en" ? "EN" : "বাং"}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setBanglaNumerals(!banglaNumerals)}
                className={cx(
                  "rounded-md px-2 py-1 text-[11px] font-bold transition",
                  banglaNumerals ? "bg-brand-600 text-white" : "text-ink-500 hover:text-ink-800",
                )}
                title={copy("banglaNumerals", lang)}
                aria-pressed={banglaNumerals}
              >
                ১২
              </button>
            </div>

            {/* Customer switcher */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setUserOpen((v) => !v)}
                className="flex items-center gap-2 rounded-lg border border-ink-200 bg-white px-2.5 py-1.5 text-left transition hover:border-brand-300"
              >
                <span className="grid h-6 w-6 place-items-center rounded-md bg-ink-900 text-[10px] font-bold text-white">
                  {currentUser?.occupation.slice(0, 2).toUpperCase() ?? "—"}
                </span>
                <span className="hidden min-w-0 sm:block">
                  <span className="block truncate text-[11px] leading-tight font-bold text-ink-900">
                    {currentUser
                      ? `${lang === "bn" ? "গ্রাহক" : "Customer"} ${currentUser.user_id.replace("U", "")}`
                      : "…"}
                  </span>
                  <span className="tabular block text-[10px] leading-tight text-ink-400">
                    {currentUser?.occupation ?? ""}
                  </span>
                </span>
              </button>
              {userOpen ? (
                <div className="animate-in absolute right-0 z-50 mt-2 max-h-[70vh] w-[310px] overflow-y-auto rounded-xl border border-ink-200 bg-white p-2 shadow-[var(--shadow-pop)]">
                  <div className="mb-2 px-2 text-[10px] font-bold tracking-wider text-ink-400 uppercase">
                    {copy("switchCustomer", lang)} · {users.length}
                  </div>
                  {users.map((u) => {
                    const p = personaLabel[u.persona];
                    const active = u.user_id === userId;
                    return (
                      <button
                        key={u.user_id}
                        type="button"
                        onClick={() => setUserId(u.user_id)}
                        className={cx(
                          "flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left transition",
                          active ? "bg-brand-50" : "hover:bg-ink-50",
                        )}
                      >
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500 opacity-0" data-active={active} />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center justify-between gap-2">
                            <span className="truncate text-[12px] font-bold text-ink-900">
                              {u.user_id}
                            </span>
                            <span className="tabular shrink-0 text-[10px] text-ink-400">{p.en}</span>
                          </span>
                          <span className="mt-0.5 block truncate text-[11px] leading-snug text-ink-500">
                            {u.occupation} · {u.location_type} · {u.age_group}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                  <div className="mt-2 border-t border-ink-100 px-2 pt-2 text-[10px] leading-relaxed text-ink-400">
                    {lang === "bn"
                      ? "ডেমো কোহর্টের নকশা-লেবেল (কোনো ইঞ্জিনের ইনপুট নয়): "
                      : "Cohort design labels (never used as engine input): "}
                    {Object.entries(personas)
                      .map(([k, n]) => `${personaLabel[k as keyof typeof personaLabel].en} (${n})`)
                      .join(" · ")}
                  </div>
                </div>
              ) : null}
            </div>

            <NavLink
              to="/assistant"
              className={({ isActive }) =>
                cx(
                  "hidden items-center gap-1.5 rounded-lg px-3 py-2 text-[12px] font-bold transition sm:flex",
                  isActive ? "bg-brand-600 text-white" : "bg-ink-900 text-white hover:bg-brand-600",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive ? <Bot className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                  {copy("assistant", lang)}
                </>
              )}
            </NavLink>
            <button type="button" onClick={() => void logout()} className="hidden rounded-lg border border-ink-200 px-3 py-2 text-[12px] font-bold text-ink-600 hover:border-brand-300 hover:text-brand-700 sm:block">
              {lang === "bn" ? "লগআউট" : "Log out"}
            </button>
          </div>
        </div>
        <div className="border-t border-ink-100 bg-ink-50/70">
          <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5 text-[10px] text-ink-500">
            <span className="font-semibold text-ink-600">
              {copy("asOf", lang)}:{" "}
              <span className={lang === "bn" ? "bn" : undefined}>
                {ctx ? fullDate(ctx.asOf, banglaNumerals ? "bn" : lang) : "—"}
              </span>
            </span>
            {ctx ? (
              <span className="tabular">
                {copy("liquidBalance", lang)}: {taka(ctx.liquidBalance, { lang: banglaNumerals ? "bn" : lang })}
              </span>
            ) : null}
            <span className="ml-auto text-ink-400">{lang === "bn" ? "নিরাপদ API ডেটা" : "Secure API data"}</span>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1600px]">
        {/* Sidebar */}
        <aside
          className={cx(
            "no-print fixed inset-y-0 left-0 z-50 w-[262px] shrink-0 overflow-y-auto border-r border-ink-200 bg-white p-4 pt-4 lg:sticky lg:top-[89px] lg:z-10 lg:h-[calc(100vh-89px)] lg:translate-x-0",
            navOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <nav className="space-y-5">
            {NAV.map((group) => (
              <div key={group.key}>
                <div className="mb-1.5 px-2 text-[10px] font-bold tracking-wider text-ink-400 uppercase">
                  {copy(group.key, lang)}
                </div>
                <div className="space-y-0.5">
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    return (
                      <NavLink
                        key={item.to}
                        to={item.to}
                        end={item.to === "/"}
                        onClick={() => setNavOpen(false)}
                        className={({ isActive }) =>
                          cx(
                            "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-semibold transition",
                            isActive
                              ? "bg-brand-50 text-brand-700"
                              : "text-ink-600 hover:bg-ink-50 hover:text-ink-900",
                            lang === "bn" && "bn",
                          )
                        }
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        {copy(item.key, lang)}
                      </NavLink>
                    );
                  })}
                </div>
              </div>
            ))}
          </nav>

          <div className="mt-6 rounded-xl border border-ink-200 bg-ink-50 p-3">
            <div className="mb-1 flex items-center gap-1.5 text-[11px] font-bold text-ink-700">
              <Landmark className="h-3.5 w-3.5" />
              {lang === "bn" ? "কীভাবে কাজ করে" : "How this works"}
            </div>
            <p className="text-[11px] leading-relaxed text-ink-500">
              {lang === "bn"
                ? "প্রতিটি সংখ্যা একটি নির্ধারিত ইঞ্জিন থেকে আসে এবং তার প্রমাণ দেখানো যায়। কোপাইলট শুধু ব্যাখ্যা করে — সিদ্ধান্ত আপনার।"
                : "Every number comes from a deterministic engine and carries its evidence. The copilot explains; the decision stays yours."}
            </p>
            <div className="mt-2">
              <Chip tone="brand">{lang === "bn" ? "ব্যাখ্যা-ভিত্তিক" : "evidence-first"}</Chip>
            </div>
          </div>
        </aside>

        {navOpen ? (
          <button
            type="button"
            aria-label="Close menu"
            className="no-print fixed inset-0 z-40 bg-ink-900/20 lg:hidden"
            onClick={() => setNavOpen(false)}
          />
        ) : null}

        <main className="min-w-0 flex-1 px-4 py-6 lg:px-8">
          <Outlet />
          <footer className="no-print mt-10 border-t border-ink-200 pt-5 text-[11px] leading-relaxed text-ink-400">
            <p>
              {lang === "bn"
                ? "upay ফিন্যান্সিয়াল লাইফ কোপাইলট একটি শিক্ষামূলক পরিকল্পনা টুল। এটি ঋণ অনুমোদন বা প্রত্যাখ্যান করে না এবং কোনো লেনদেন সম্পাদনা করে না।"
                : "upay Financial Life Copilot is an educational planning tool. It does not approve or decline credit, and it does not move money."}
            </p>
            <p className="mt-1">
              {lang === "bn" ? "সিনথেটিক ডেমো ডেটা · " : "Synthetic demo data · "}
              {ctx ? `${ctx.user.user_id} · ${ctx.transactions.length.toLocaleString("en-US")} tx` : ""}
              {banglaNumerals && lang === "en" ? ` · ${toBanglaDigits(ctx ? String(ctx.transactions.length) : "")} tx` : ""}
            </p>
          </footer>
        </main>
      </div>

      {/* Global evidence drawer — the running record of what the user has inspected. */}
      {evidenceStack.length ? (
        <div className="no-print fixed right-4 bottom-4 z-50 w-[min(24rem,calc(100vw-2rem))]">
          {drawerOpen ? (
            <div className="animate-in mb-2 max-h-[70vh] overflow-y-auto rounded-2xl border border-ink-200 bg-white p-3 shadow-lg">
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="text-[11px] font-bold tracking-wide text-ink-500 uppercase">
                  {lang === "bn" ? "দেখা প্রমাণ" : "Inspected evidence"}
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={clearEvidence}
                    className="rounded-lg border border-ink-200 px-2 py-1 text-[11px] font-semibold text-ink-600 transition hover:border-brand-300"
                  >
                    {lang === "bn" ? "মুছুন" : "Clear"}
                  </button>
                  <button
                    type="button"
                    onClick={() => popEvidence()}
                    aria-label="Close latest evidence"
                    className="rounded-lg border border-ink-200 px-2 py-1 text-[11px] font-semibold text-ink-600 transition hover:border-brand-300"
                  >
                    {lang === "bn" ? "সাম্প্রতিকটি বন্ধ" : "Dismiss latest"}
                  </button>
                </div>
              </div>
              <div className="space-y-2">
                {evidenceStack.slice(0, 3).map((e, i) => (
                  <div key={`${e.engine}-${i}`} className="rounded-xl border border-ink-100 p-2">
                    <EvidenceBody evidence={e} />
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setDrawerOpen((v) => !v)}
            className="ml-auto flex items-center gap-1.5 rounded-full bg-ink-900 px-3.5 py-2.5 text-[12px] font-bold text-white shadow-lg transition hover:bg-brand-700"
          >
            <FlaskConical className="h-3.5 w-3.5" />
            {lang === "bn" ? "প্রমাণ" : "Evidence"}
            <span className="rounded-full bg-white/20 px-1.5 tabular">{evidenceStack.length}</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}