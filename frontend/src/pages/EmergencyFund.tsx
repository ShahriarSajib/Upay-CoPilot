import { useState } from "react";
import { Info, ShieldCheck, Umbrella } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Segmented, Stat, Table } from "@/components/ui";
import { EvidenceBody, EvidenceButton } from "@/components/Evidence";
import { MoneyBars, Panel, VIZ } from "@/components/charts";
import { emergencyCompletionDate, runEmergencyPlanner } from "@/engines/emergency";
import { essentialByMonth } from "@/engines/spending";
import { bandFor } from "@/lib/format";

export default function EmergencyFund() {
  const bundle = useBundle();
  const f = useFmt();
  const { lang } = useCopilot();
  const [monthsTarget, setMonthsTarget] = useState<string>("3");

  if (!bundle) return null;
  const { ctx } = bundle;
  const plan = runEmergencyPlanner(ctx, Number(monthsTarget));
  const essentialSeries = essentialByMonth(ctx);
  const completion = emergencyCompletionDate(ctx, plan.monthlyToFund);
  const band = bandFor((plan.progress * 100) || 0);
  const covered = plan.liquidBalance >= plan.targetAmount;

  return (
    <div>
      <PageHeader
        title={copy("emergency", lang)}
        subtitle={
          f.loc === "bn"
            ? "লক্ষ্যটি একটি অনুমান — প্রতিটি সংখ্যা আপনার লেজার থেকে, এবং গুণকটি বদলে দেখা যায় কী হয়।"
            : "The target is a convention, not a rule. Every number comes from your own ledger, and the multiplier is adjustable so you can test alternatives."
        }
        actions={
          <Segmented
            value={monthsTarget}
            onChange={setMonthsTarget}
            options={[1, 2, 3, 4, 6].map((m) => ({ value: String(m), label: `${m}${f.loc === "bn" ? " মাস" : "m"}` }))}
          />
        }
      />

      <Grid cols={4} className="mb-5">
        <Card>
          <Stat
            label={f.loc === "bn" ? "এখন আছে" : "Covered today"}
            value={f.num(plan.monthsOfCoverNow, 1)}
            hint={`${f.loc === "bn" ? "মাসের প্রয়োজনীয় খরচ" : "of essential spend"}`}
            big
            tone={plan.monthsOfCoverNow >= Number(monthsTarget) ? "good" : plan.monthsOfCoverNow >= 1 ? "warn" : "bad"}
          />
        </Card>
        <Card>
          <Stat
            label={`${monthsTarget}${f.loc === "bn" ? " মাসের লক্ষ্য" : "-month target"}`}
            value={f.taka(plan.targetAmount)}
            big
            hint={`${f.loc === "bn" ? "সম্ভাব্য ব্যাপ্তি" : "plausible range"} ${f.taka(plan.targetLow)}–${f.taka(plan.targetHigh)}`}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "আর জমাতে হবে" : "Still to fund"}
            value={f.taka(plan.remaining)}
            tone={plan.remaining > 0 ? "warn" : "good"}
            hint={
              plan.monthsToFund > 0 && plan.monthlyToFund > 0
                ? `${f.loc === "bn" ? "মাসে" : "at"} ${f.taka(plan.monthlyToFund)} → ${f.num(plan.monthsToFund)} ${copy("months", lang)}`
                : f.loc === "bn" ? "প্রতি মাসে অতিরিক্ত সঞ্চয় নেই" : "no spare surplus per month"
            }
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "সম্পন্ন হওয়ার তারিখ" : "Completion date"}
            value={completion ? f.month(completion) : "—"}
            big
            tone={completion ? "good" : "warn"}
            hint={completion ? f.loc === "bn" ? "বর্তমান গতিতে" : "at the current surplus" : copy("noData", lang)}
          />
        </Card>
      </Grid>

      <Grid cols={3} className="mb-5">
        <Card className="sm:col-span-2">
          <CardHeader
            kicker={f.loc === "bn" ? "অগ্রগতি" : "Progress"}
            title={f.loc === "bn" ? "লক্ষ্যের দিকে যেখানে আছেন" : "Where you are against the target"}
            right={<EvidenceButton evidence={plan.evidence} />}
          />
          <div className="mb-1 flex items-baseline justify-between">
            <span className="tabular text-[30px] leading-none font-black tracking-[-0.02em] text-ink-900">
              {f.percent(plan.progress, 0)}
            </span>
            <span className="text-[12px] font-semibold text-ink-500">
              {f.taka(plan.saved)} / {f.taka(plan.targetAmount)}
            </span>
          </div>
          <Meter value={plan.progress * 100} tone={covered ? "good" : plan.progress > 0.4 ? "warn" : "bad"} />
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <Stat
              label={f.loc === "bn" ? "মাসিক প্রয়োজনীয় খরচ" : "Essential monthly spend"}
              value={f.taka(plan.essentialMonthly)}
              hint={f.loc === "bn" ? "খাতভিত্তিক ওজনযুক্ত" : "category-weighted, not declared"}
            />
            <Stat
              label={f.loc === "bn" ? "বাস্তবে জমানোর সক্ষমতা" : "Realistic monthly contribution"}
              value={f.taka(plan.monthlyToFund)}
              hint={f.loc === "bn" ? "গড় মাসিক অতিশেষ" : "mean of monthly surplus"}
            />
          </div>

          <div className="mt-5 rounded-xl border border-ink-200 bg-ink-50 p-3.5">
            <div className="mb-1 text-[11px] font-semibold tracking-wide text-ink-400 uppercase">
              {f.loc === "bn" ? "গুণক বদলে দেখুন" : "Change the multiplier"}
            </div>
            <div className="grid gap-2 sm:grid-cols-5">
              {[1, 2, 3, 4, 6].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMonthsTarget(String(m))}
                  className={
                    Number(monthsTarget) === m
                      ? "rounded-lg border border-brand-300 bg-brand-50 px-2 py-2 text-left"
                      : "rounded-lg border border-ink-200 bg-white px-2 py-2 text-left hover:border-ink-300"
                  }
                >
                  <div className="text-[11px] font-bold text-ink-500">
                    {m} {f.loc === "bn" ? "মাস" : "month"}
                  </div>
                  <div className="tabular text-[13px] font-bold text-ink-900">{f.taka(plan.essentialMonthly * m)}</div>
                </button>
              ))}
            </div>
            <p className="mt-2 text-[11.5px] leading-relaxed text-ink-500">
              {f.loc === "bn"
                ? "এক-আয়ের পরিবারে ১ মাসই যথেষ্ট হতে পারে; অনিয়মিত আয়ে ৬ মাস বাস্তবসম্মত। কোনটি আপনার পরিস্থিতির জন্য উপযুক্ত তা আপনি ভালো জানেন।"
                : "One month can be enough for a household with support; six can be realistic for volatile income. Which applies is your judgement, not the app's."}
            </p>
          </div>
        </Card>

        <Panel
          title={f.loc === "bn" ? "প্রয়োজনীয় খরচের ইতিহাস" : "Essential spend over time"}
          subtitle={f.loc === "bn" ? "প্রতি মাসের অনুমান" : "per month, as estimated"}
          height={240}
        >
          <MoneyBars
            lang={f.tlang}
            height={240}
            xKey="key"
            xTick={(v) => f.month(v)}
            data={ctx.monthly.map((m, i) => ({
              key: m.key,
              essential: Math.round(essentialSeries[i] ?? 0),
              spend: Math.round(m.spend),
            }))}
            keys={[
              { key: "essential", label: f.loc === "bn" ? "প্রয়োজনীয়" : "essential", color: VIZ[0] },
              { key: "spend", label: f.loc === "bn" ? "মোট ব্যয়" : "total spend", color: VIZ[2] },
            ]}
          />
          <p className="mt-2 text-[11.5px] leading-relaxed text-ink-500">
            {f.loc === "bn"
              ? `ব্যাপ্তি ${f.taka(plan.essentialLow)}–${f.taka(plan.essentialHigh)} (২৫তম থেকে ৭৫তম শতাংশ)। লক্ষ্যটি এই ব্যাপ্তির মাঝামাঝি ধরে হিসাব করা।`
              : `The band runs ${f.taka(plan.essentialLow)}–${f.taka(plan.essentialHigh)} (25th–75th percentile). The target is anchored to the middle of that range rather than a single confident number.`}
          </p>
        </Panel>
      </Grid>

      {covered ? (
        <div className="mb-5">
          <Banner tone="good" title={f.loc === "bn" ? "লক্ষ্য পূরণ হয়েছে" : "Target reached"} icon={<ShieldCheck className="h-4 w-4" />}>
            <p>
              {f.loc === "bn"
                ? `তরল ব্যালেন্স এখন ${f.num(plan.monthsOfCoverNow, 1)} মাসের প্রয়োজনীয় খরচ ঢাকছে — লক্ষ্যের বেশি। এখন এই অংশটিকে লক্ষ্যে বরাদ্দ না করে আলাদা রাখাই সাধারণত ভালো।`
                : `The liquid balance covers ${f.num(plan.monthsOfCoverNow, 1)} months of essential spend, past the ${monthsTarget}-month target. Keeping this slice separate from goal money is usually the better habit.`}
            </p>
          </Banner>
        </div>
      ) : null}

      <Card className="mb-5">
        <CardHeader
          kicker={f.loc === "bn" ? "কেন এই সংখ্যা" : "Why this number"}
          title={f.loc === "bn" ? "প্রতিটি ধাপের হিসাব" : "Every step of the calculation"}
        />
        <Table
          align="right"
          head={[
            f.loc === "bn" ? "ধাপ" : "Step",
            f.loc === "bn" ? "কীভাবে" : "How it is derived",
            f.loc === "bn" ? "ফলাফল" : "Result",
          ]}
          rows={[
            [
              f.loc === "bn" ? "প্রয়োজনীয় মাসিক ব্যয়" : "Essential monthly spend",
              f.loc === "bn" ? "প্রতিটি খাতের প্রয়োজনীয় অংশ × মাসের ব্যয়" : "category essential share × monthly spend",
              f.taka(plan.essentialMonthly),
            ],
            [
              f.loc === "bn" ? `${monthsTarget} মাসের লক্ষ্য` : `${monthsTarget}-month target`,
              f.loc === "bn" ? "প্রয়োজনীয় মাসিক ব্যয় × ৩" : "essential monthly × multiplier",
              f.taka(plan.targetAmount),
            ],
            [
              f.loc === "bn" ? "তরল ব্যালেন্স" : "Liquid balance",
              f.loc === "bn" ? "upay + ব্যাংক + নগদ ওয়ালেট" : "upay + bank + cash wallets",
              f.taka(plan.liquidBalance),
            ],
            [
              f.loc === "bn" ? "ঘাটতি" : "Gap",
              f.loc === "bn" ? "লক্ষ্য − বর্তমান ব্যালেন্স" : "target − current balance",
              f.taka(plan.remaining),
            ],
            [
              f.loc === "bn" ? "মাসিক জমা" : "Monthly contribution",
              f.loc === "bn" ? "গড় মাসিক অতিশেষ, ঘাটতির সীমানা" : "mean monthly surplus, capped at the gap",
              f.taka(plan.monthlyToFund),
            ],
            [
              f.loc === "bn" ? "সময় লাগবে" : "Months needed",
              f.loc === "bn" ? "ঘাটতি ÷ মাসিক জমা" : "gap ÷ monthly contribution",
              plan.monthsToFund > 0 ? `${f.num(plan.monthsToFund)} ${copy("months", lang)}` : "—",
            ],
          ]}
        />
        <p className="mt-3 text-[11.5px] leading-relaxed text-ink-500">
          {f.loc === "bn"
            ? `বর্তমান ব্যান্ড: ${band}। তরল ব্যালেন্স ধরে নেওয়া হয়েছে পুরোটা জমানো হিসেবে — আংশিক লকদা বা নির্দিষ্ট উদ্দেশ্যে বাঁধা টাকা এখানে ধরা হয়নি।`
            : `Current band: ${band}. The whole liquid balance is counted as available; restricted or committed funds are not modelled, so treat the target as a floor rather than a ceiling.`}
        </p>
      </Card>

      <Card>
        <CardHeader
          kicker={copy("evidence", lang)}
          title={plan.evidence.headline}
          right={<Chip tone="neutral">{Math.round(plan.evidence.confidence * 100)}% {copy("confidence", lang)}</Chip>}
        />
        <EvidenceBody evidence={plan.evidence} />
        <div className="mt-4 flex items-start gap-2 text-[11.5px] leading-relaxed text-ink-500">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <p className="flex items-center gap-1.5">
            <Umbrella className="h-3.5 w-3.5" />
            {f.loc === "bn"
              ? "এটি একটি পরিকল্পনার হিসাব, কোনো বিনিয়োগ বা বীমা পণ্যের পরামর্শ নয়।"
              : "This is a planning calculation, not a recommendation to buy any product."}
          </p>
        </div>
      </Card>
    </div>
  );
}