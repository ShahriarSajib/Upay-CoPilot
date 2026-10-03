import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Lightbulb,
  Mic,
  ShieldQuestion,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import type { Insight } from "@/types";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Stat, cx } from "@/components/ui";
import { EvidenceButton } from "@/components/Evidence";
import { AreaTrend, Donut, ForecastChart, MonthlyFlowChart, Panel, VIZ } from "@/components/charts";

export default function Dashboard() {
  const bundle = useBundle();
  const { lang } = useCopilot();
  const f = useFmt();
  if (!bundle) return null;
  const { ctx, health, spending, forecast30, shortage, shortageRisk, goals, actions, insights, cashOut } = bundle;
  const bn = lang === "bn";

  const topInsights = insights.slice(0, 3);
  const recent = ctx.daily.slice(-60);
  /** Walk the daily net flow backwards from today's closing balance. */
  const balanceSeries = recent
    .reduce<{ date: string; balance: number }[]>((acc, d) => {
      const prev = acc.length ? acc[acc.length - 1].balance : ctx.liquidBalance;
      acc.push({ date: d.iso, balance: Math.max(0, Math.round(prev + d.net)) });
      return acc;
    }, [])
    .reverse();
  const monthly = ctx.monthly.map((m) => ({ key: m.key, income: m.income, spend: m.spend, savings: m.savings }));

  return (
    <div>
      <PageHeader
        title={copy("appName", lang)}
        subtitle={copy("appTagline", lang)}
        actions={
          <>
            <Link
              to="/assistant"
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-[13px] font-bold text-white transition hover:bg-brand-700"
            >
              <Mic className="h-4 w-4" />
              {copy("assistant", lang)}
            </Link>
            <Link
              to="/review"
              className="inline-flex items-center gap-2 rounded-lg border border-ink-200 bg-white px-3.5 py-2 text-[13px] font-semibold text-ink-700 transition hover:border-brand-300"
            >
              <CalendarClock className="h-4 w-4" />
              {copy("review", lang)}
            </Link>
          </>
        }
      />

      {/* Profile strip — observable profile fields only. The generator's persona
          label is ground truth, so it stays on the Evaluation page. */}
      <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-ink-200 bg-white px-4 py-3 text-[12px] text-ink-600">
        <span className="inline-flex items-center gap-1.5 font-bold text-ink-800">
          <Sparkles className="h-3.5 w-3.5 text-brand-500" />
          {f.loc === "bn" ? "আপনার প্রোফাইল" : "Your profile"}
        </span>
        <span className="text-ink-500">
          {f.loc === "bn"
            ? "নিচের সব সংখ্যা এই লেজার থেকে হিসাব করা — কোনো ডেমো লেবেল বা আগে থেকে ঠিক করা ধরন ব্যবহার করা হয়নি।"
            : "Every number below is computed from this ledger. No demo label or pre-assigned archetype is used to produce them."}
        </span>
        <Chip tone="neutral" className="ml-auto">
          {ctx.user.occupation} · {ctx.user.location_type} · {ctx.user.age_group}
        </Chip>
      </div>

      {/* Hero row */}
      <Grid cols={4} className="mb-5">
        <Card className="relative overflow-hidden">
          <div className="pointer-events-none absolute -top-8 -right-6 h-28 w-28 rounded-full bg-brand-50" />
          <div className="relative">
            <div className="text-[11px] font-semibold tracking-wide text-ink-400 uppercase">{copy("health", lang)}</div>
            <div className="mt-1 flex items-end gap-2">
              <span className="tabular text-[40px] leading-none font-black tracking-[-0.03em] text-ink-900">{health.score}</span>
              <span className="mb-1 text-[13px] font-semibold text-ink-400">/100</span>
            </div>
            <div className="mt-2">
              <Meter
                value={health.score}
                tone={health.score >= 68 ? "good" : health.score >= 45 ? "warn" : "bad"}
                label={
                  <span className="text-[12px] font-bold text-ink-700">
                    {f.bi(
                      { strong: "Strong", good: "Good", moderate: "Moderate", weak: "Weak", critical: "Critical" }[health.band],
                      { strong: "শক্তিশালী", good: "ভালো", moderate: "মাঝারি", weak: "দুর্বল", critical: "সংকটজনক" }[health.band],
                    )}
                  </span>
                }
              />
            </div>
            <div className="mt-3">
              <EvidenceButton evidence={health.evidence} />
            </div>
          </div>
        </Card>

        <Card>
          <Stat
            label={copy("liquidBalance", lang)}
            value={f.taka(ctx.liquidBalance)}
            hint={`${copy("upayBalance", lang)} ${f.taka(ctx.upayBalance)}`}
            big
          />
          <div className="mt-3">
            <EvidenceButton evidence={bundle.forecast30.evidence} />
          </div>
        </Card>

        <Card>
          <Stat
            label={`${copy("thisMonth", lang)} · ${copy("spending", lang)}`}
            value={f.taka(ctx.currentMonth.spend)}
            hint={
              <span className="inline-flex items-center gap-1">
                {ctx.previousMonth && ctx.previousMonth.spend > 0 ? (
                  <>
                    {ctx.currentMonth.spend >= ctx.previousMonth.spend ? (
                      <TrendingUp className="h-3 w-3 text-brand-500" />
                    ) : (
                      <TrendingDown className="h-3 w-3 text-mint-600" />
                    )}
                    {f.percent(ctx.currentMonth.spend / ctx.previousMonth.spend - 1, 1)} {copy("vsLastMonth", lang)}
                  </>
                ) : (
                  copy("noData", lang)
                )}
              </span>
            }
            big
          />
          <div className="mt-3">
            <EvidenceButton evidence={spending.evidence} />
          </div>
        </Card>

        <Card>
          <Stat
            label={copy("savingsRate", lang)}
            value={f.percent(
              ctx.monthlyIncomeAvg > 0 ? (ctx.monthlyIncomeAvg - ctx.monthlySpendAvg) / ctx.monthlyIncomeAvg : 0,
              1,
            )}
            hint={`${f.taka(Math.max(0, ctx.monthlyIncomeAvg - ctx.monthlySpendAvg))} ${copy("monthly", lang)}`}
            tone={
              ctx.monthlyIncomeAvg > 0 && (ctx.monthlyIncomeAvg - ctx.monthlySpendAvg) / ctx.monthlyIncomeAvg >= 0.15
                ? "good"
                : "warn"
            }
            big
          />
<div className="mt-3">
              <EvidenceButton evidence={health.evidence} />
            </div>
          </Card>
        </Grid>

      {/* Main grid */}
      <Grid cols={3} className="mb-5">
        <Panel
          title={copy("forecast", lang)}
          subtitle={`${forecast30.horizonDays} ${copy("days", lang)} · ${f.bi(forecast30.method.split(" ×")[0], "ইঞ্জিন-ভিত্তিক মডেল")}`}
          right={<Link to="/forecast" className="text-[12px] font-bold text-brand-600 hover:underline">{copy("evaluate", lang)} →</Link>}
          height={230}
        >
          <ForecastChart points={forecast30.points} lang={f.tlang} buffer={forecast30.buffer} height={230} />
        </Panel>

        <Panel
          title={copy("cash_dependency", lang)}
          subtitle={`${f.percent(cashOut.shareOfSpend, 0)} ${copy("ofSpend", lang)} ${bn ? "নগদে" : "in cash"}`}
          right={<Link to="/cash-out" className="text-[12px] font-bold text-brand-600 hover:underline">→</Link>}
          height={230}
        >
          <Donut
            data={[
              { name: bn ? "নগদে" : "Cash", value: cashOut.cashSettledSpend },
              { name: bn ? "ডিজিটাল" : "Digital", value: Math.max(0, ctx.monthlySpendAvg * ctx.monthly.length - cashOut.cashSettledSpend) },
            ]}
            lang={f.tlang}
            centerValue={f.percent(cashOut.shareOfSpend, 0)}
            centerLabel={bn ? "নগদে ব্যয়" : "cash spend"}
          />
        </Panel>

        <Panel
          title={copy("goals", lang)}
          subtitle={`${goals.goals.length} ${bn ? "টি লক্ষ্য" : "goals"} · ${f.percent(goals.progress, 0)} ${bn ? "জমা" : "funded"}`}
          right={<Link to="/goals" className="text-[12px] font-bold text-brand-600 hover:underline">→</Link>}
          height={230}
        >
          <div className="space-y-3">
            {goals.feasibility.slice(0, 3).map((g) => (
              <Link key={g.goal.goal_id} to="/goals" className="block">
                <div className="mb-1 flex items-baseline justify-between gap-2">
                  <span className="truncate text-[12px] font-semibold text-ink-800">{g.goal.goal_name}</span>
                  <span className="tabular shrink-0 text-[11px] text-ink-500">{f.percent(g.probability, 0)}</span>
                </div>
                <Meter
                  value={g.probability * 100}
                  tone={g.probability >= 0.7 ? "good" : g.probability >= 0.4 ? "warn" : "bad"}
                />
                <div className="mt-1 text-[11px] text-ink-400">
                  {g.goal.target_date} · {g.monthsLeft} {copy("months", lang)}
                </div>
              </Link>
            ))}
            {goals.feasibility.length === 0 ? <p className="text-[12px] text-ink-400">{copy("noData", lang)}</p> : null}
          </div>
        </Panel>
      </Grid>

      {/* Month-end shortage callout */}
      {shortageRisk === "elevated" || shortageRisk === "high" ? (
        <div className="mb-5">
          <Banner tone="warn" title={`${copy("forecast_shortage", lang)} · ${shortageRisk}`} icon={<AlertTriangle className="h-4 w-4" />}>
            <p>
              {f.percent(shortage.lateShare, 0)} {bn ? "ব্যয় ২০ তারিখের পরে হয়" : "of spending lands after day 20"} ·{" "}
              {bn ? "প্রকৃতিপত সর্বনিম্ন ব্যালেন্স" : "projected minimum balance"} {f.taka(shortage.projectedMinBalance)}{" "}
              {bn ? "বনাম" : "vs"} {bn ? "রিজার্ভ" : "buffer"} {f.taka(shortage.buffer)}.
            </p>
            <Link to="/forecast" className="mt-1 inline-flex items-center gap-1 font-bold text-brand-700 hover:underline">
              {bn ? "কী করবেন দেখুন" : "See what to change"} <ArrowRight className="h-3 w-3" />
            </Link>
          </Banner>
        </div>
      ) : null}

      {/* Insights */}
      <section className="mb-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-[16px] font-bold text-ink-900">{bn ? "আজকের বিশ্লেষণ" : "Today's read of your money"}</h2>
          <span className="text-[11px] text-ink-400">{bn ? "প্রতিটি ফলাফল প্রমাণসহ" : "every card carries its evidence"}</span>
        </div>
        <Grid cols={3}>
          {topInsights.map((i) => (
            <InsightCard key={i.id} insight={i} />
          ))}
        </Grid>
      </section>

      {/* Action centre */}
      <Grid cols={3} className="mb-5">
        <div className="sm:col-span-2">
          <Card>
            <CardHeader
              kicker={bn ? "অ্যাকশন সেন্টার" : "Action centre"}
              title={bn ? "এখনই করুন / পরিকল্পনা করুন" : "Do now, plan next, just watch"}
              subtitle={
                bn
                  ? "অগ্রাধিকার দেওয়া হয়েছে বাস্তবসম্মত পরিবর্তনের ওপর — উপদেশ নয়।"
                  : "Ranked by the size of the effect on your balance, not by what is easiest to say."
              }
            />
            <ol className="space-y-2.5">
              {actions.slice(0, 5).map((a) => (
                <li key={a.id} className="flex items-start gap-3 rounded-xl border border-ink-200 px-3.5 py-3">
                  <span
                    className={cx(
                      "tabular mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-lg text-[11px] font-black",
                      a.priority === "do-now"
                        ? "bg-brand-600 text-white"
                        : a.priority === "plan"
                          ? "bg-ink-900 text-white"
                          : "bg-ink-100 text-ink-600",
                    )}
                  >
                    {a.rank}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[13px] font-bold text-ink-900">{f.bi(a.title, a.titleBn)}</span>
                      <Chip tone={a.priority === "do-now" ? "bad" : a.priority === "plan" ? "brand" : "neutral"}>
                        {a.priority}
                      </Chip>
                      {a.amount ? <Chip tone="neutral">{f.taka(a.amount)}</Chip> : null}
                    </div>
                    <p className="mt-1 text-[12px] leading-relaxed text-ink-600">{f.bi(a.why, a.whyBn)}</p>
                    <p className="mt-1 text-[12px] leading-relaxed text-ink-800">
                      <span className="font-bold">{bn ? "করবেন:" : "Do:"}</span> {f.bi(a.doThis, a.doThisBn)}
                    </p>
                    <div className="mt-1.5">
                      <EvidenceButton evidence={a.evidence} />
                    </div>
                  </div>
                  {a.route ? (
                    <Link
                      to={a.route}
                      className="mt-0.5 inline-flex shrink-0 items-center gap-1 self-center rounded-lg border border-ink-200 px-2.5 py-1.5 text-[11px] font-bold text-ink-700 transition hover:border-brand-300 hover:text-brand-700"
                    >
                      {bn ? "খুলুন" : "Open"} <ArrowRight className="h-3 w-3" />
                    </Link>
                  ) : null}
                </li>
              ))}
            </ol>
          </Card>
        </div>

        <div className="space-y-4">
          <Panel title={bn ? "মাসের ছবি" : "Twelve months at a glance"} height={200}>
            <MonthlyFlowChart data={monthly} lang={f.tlang} height={200} />
          </Panel>
          <Panel title={bn ? "দৈনিক ব্যালেন্স" : "Last 60 days"} height={170}>
            <AreaTrend
              data={balanceSeries}
              keys={[{ key: "balance", label: bn ? "ব্যালেন্স" : "balance", color: VIZ[0] }]}
              lang={f.tlang}
              height={170}
            />
          </Panel>
        </div>
      </Grid>

      {/* Ask upay strip */}
      <Card className="mb-5">
        <CardHeader
          kicker={bn ? "অ্যাস্ক আপয়" : "Ask upay"}
          title={bn ? "যেকোনো প্রশ্নের উত্তর, প্রমাণসহ" : "Any question, answered with the working shown"}
          subtitle={
            bn
              ? "ইংরেজা, বাংলা বা বাংলিশে লিখুন — কিংবা মাইকে বলুন।"
              : "Write in English, বাংলা or Banglish — or just press the mic."
          }
          right={
            <Link
              to="/assistant"
              className="inline-flex items-center gap-2 rounded-lg bg-ink-900 px-3.5 py-2 text-[13px] font-bold text-white transition hover:bg-brand-600"
            >
              <Mic className="h-4 w-4" />
              {bn ? "জিজ্ঞাসা করুন" : "Ask a question"}
            </Link>
          }
        />
        <div className="flex flex-wrap gap-2">
          {[
            { en: "Why is my spending up this month?", bn: "এই মাসে খরচ কেন বেড়েছে?", to: "/assistant" },
            { en: "Will I run short before month-end?", bn: "মাস শেষে টাকা থাকবে?", to: "/assistant" },
            { en: "Can I save 30,000 in 6 months?", bn: "৬ মাসে ৩০ হাজার জমাতে পারব?", to: "/assistant" },
            { en: "How does Request Money work?", bn: "রিকোয়েস্ট মানি কীভাবে কাজ করে?", to: "/assistant" },
            { en: "How much do I cash out?", bn: "কত নগদ বের করি?", to: "/cash-out" },
          ].map((s) => (
            <Link
              key={s.en}
              to={s.to}
              className={cx(
                "rounded-full border border-ink-200 bg-white px-3 py-1.5 text-[12px] font-semibold text-ink-700 transition hover:border-brand-300 hover:text-brand-700",
                lang === "bn" && "bn",
              )}
            >
              {f.bi(s.en, s.bn)}
            </Link>
          ))}
        </div>
      </Card>

      {/* Balance-of-life footer strip */}
      <Grid cols={3}>
        <MiniTile
          icon={<CheckCircle2 className="h-4 w-4 text-mint-600" />}
          title={bn ? "জরুরি তহবিল" : "Emergency cover"}
          value={f.num(health.emergencyMonths, 1)}
          suffix={bn ? "মাস" : "months"}
          to="/emergency-fund"
          note={bn ? "প্রয়োজনীয় ব্যয়ের" : "of essential spend"}
        />
        <MiniTile
          icon={<ShieldQuestion className="h-4 w-4 text-viz-5" />}
          title={bn ? "সহনশীলতা" : "Resilience"}
          value={f.num(bundle.resilience.score)}
          suffix="/100"
          to="/resilience"
          note={`${f.num(bundle.resilience.shockTolerance, 1)}× ${bn ? "জরুরি সামলাতে পারেন" : "shock tolerance"}`}
        />
        <MiniTile
          icon={<Lightbulb className="h-4 w-4 text-viz-4" />}
          title={bn ? "শেখার সুযোগ" : "Learning"}
          value={f.num(bundle.literacy.length)}
          suffix={bn ? "টি পাঠ" : "lessons"}
          to="/learning"
          note={bundle.literacy[0] ? f.bi(bundle.literacy[0].topic.title, bundle.literacy[0].topic.titleBn) : copy("noData", lang)}
        />
      </Grid>
    </div>
  );
}

function InsightCard({ insight }: { insight: Insight }) {
  const f = useFmt();
  const tone =
    insight.kind === "warning" ? "border-brand-200 bg-brand-50/40" : insight.kind === "positive" ? "border-mint-100 bg-mint-50/40" : "border-ink-200 bg-white";
  return (
    <article className={cx("card p-5", tone)}>
      <div className="mb-2 flex items-center gap-2">
        {insight.kind === "warning" ? (
          <AlertTriangle className="h-4 w-4 text-brand-600" />
        ) : insight.kind === "positive" ? (
          <CheckCircle2 className="h-4 w-4 text-mint-600" />
        ) : (
          <Lightbulb className="h-4 w-4 text-viz-4" />
        )}
        <span className="text-[11px] font-bold tracking-wide text-ink-500 uppercase">{insight.engine}</span>
      </div>
      <h3 className="text-[14px] leading-snug font-bold text-ink-900">{f.bi(insight.title, insight.titleBn)}</h3>
      <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-600">{f.bi(insight.body, insight.bodyBn)}</p>
      <div className="mt-3">
        <EvidenceButton evidence={insight.evidence} />
      </div>
    </article>
  );
}

function MiniTile({
  icon,
  title,
  value,
  suffix,
  note,
  to,
}: {
  icon: React.ReactNode;
  title: string;
  value: string;
  suffix: string;
  note: string;
  to: string;
}) {
  return (
    <Link to={to} className="card flex items-center gap-3 p-4 transition hover:border-brand-300">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ink-50">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[11px] font-semibold tracking-wide text-ink-400 uppercase">{title}</span>
        <span className="mt-0.5 block text-[16px] font-bold text-ink-900">
          {value} <span className="text-[11px] font-semibold text-ink-400">{suffix}</span>
        </span>
        <span className="block truncate text-[11px] text-ink-500">{note}</span>
      </span>
      <ArrowRight className="h-4 w-4 shrink-0 text-ink-300" />
    </Link>
  );
}