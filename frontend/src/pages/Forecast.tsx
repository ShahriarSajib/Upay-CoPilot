import { useState } from "react";
import { AlertTriangle, Gauge, Info, TrendingDown } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Segmented, Stat, Table } from "@/components/ui";
import { EvidenceBody, EvidenceButton } from "@/components/Evidence";
import { ForecastChart, MoneyBars, Panel, VIZ } from "@/components/charts";
import { HORIZONS, runForecast } from "@/engines/forecast";
import { fullDate } from "@/lib/format";

export default function Forecast() {
  const bundle = useBundle();
  const f = useFmt();
  const { lang } = useCopilot();
  const [horizon, setHorizon] = useState<number>(30);

  if (!bundle) return null;
  const { ctx, forecast30, forecast90, monthEnd, shortage, shortageRisk, backtest } = bundle;
  const fc = horizon === 90 ? forecast90 : horizon === 30 ? forecast30 : runForecast(ctx, horizon);
  const risky = forecast30.lowBalanceWindows.length > 0;

  return (
    <div>
      <PageHeader
        title={copy("forecast", lang)}
        subtitle={
          f.loc === "bn"
            ? "দুটি মডেল একসাথে চালানো হয় — আপনার সাম্প্রতিক গড়, আর মৌসুম-সচেতন মডেল — যাতে বাস্তবতার সঙ্গে তুলনা করা যায়।"
            : "Two models run side by side: the recent-average a customer would eyeball, and a seasonality-aware model. The gap between them is the honest uncertainty."
        }
        actions={
          <Segmented
            value={String(horizon)}
            onChange={(v) => setHorizon(Number(v))}
            options={HORIZONS.map((h) => ({ value: String(h), label: `${h} ${copy("days", lang)}` }))}
          />
        }
      />

      <Grid cols={4} className="mb-5">
        <Card>
          <Stat
            label={f.loc === "bn" ? "আজকের তরল ব্যালেন্স" : "Liquid balance today"}
            value={f.taka(ctx.liquidBalance)}
            big
            hint={f.fullDate(ctx.asOf)}
          />
        </Card>
        <Card>
          <Stat
            label={`${horizon} ${copy("days", lang)} ${f.loc === "bn" ? "আয়" : "income"}`}
            value={f.taka(fc.expectedIncome)}
            tone="good"
            hint={f.loc === "bn" ? "নিয়মিত ও অনিয়মিত মিলিয়ে" : "scheduled + irregular"}
          />
        </Card>
        <Card>
          <Stat
            label={`${horizon} ${copy("days", lang)} ${f.loc === "bn" ? "ব্যয়" : "spending"}`}
            value={f.taka(fc.expectedExpense)}
            hint={`${f.loc === "bn" ? "দৈনিক গড়" : "daily rate"} ${f.taka(fc.expectedExpense / Math.max(1, horizon))} · ${f.loc === "bn" ? "বাধ্যতামূলক" : "obligations"} ${f.taka(fc.points.reduce((a, p) => a + p.recurringDue, 0))}`}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "শেষ ব্যালেন্স (প্রকৃতিপত)" : "Projected closing"}
            value={f.taka(fc.expectedEndingBalance)}
            tone={fc.expectedEndingBalance < fc.buffer ? "bad" : "good"}
            big
            hint={`${f.loc === "bn" ? "সর্বনিম্ন" : "trough"} ${f.taka(fc.minBalance)} ${fc.minBalanceDate ? `· ${fullDate(fc.minBalanceDate, f.tlang)}` : ""}`}
          />
        </Card>
      </Grid>

      {risky ? (
        <div className="mb-5">
          <Banner tone="warn" title={`${copy("forecast_shortage", lang)} · ${shortageRisk}`} icon={<AlertTriangle className="h-4 w-4" />}>
            <p>
              {f.loc === "bn"
                ? `${f.fullDate(fc.lowBalanceWindows[0].from)} থেকে ${f.fullDate(fc.lowBalanceWindows[0].to)} পর্যন্ত ব্যালেন্স ${f.taka(fc.buffer)} রিজার্ভের নিচে নামার সম্ভাবনা আছে।`
                : `The model puts the balance under the ${f.taka(fc.buffer)} buffer between ${f.fullDate(fc.lowBalanceWindows[0].from)} and ${f.fullDate(fc.lowBalanceWindows[0].to)}. Late-month spending is ${f.percent(shortage.lateShare, 0)} of the month.`}
            </p>
          </Banner>
        </div>
      ) : null}

      <div className="mb-5">
        <Panel
          title={f.loc === "bn" ? `${horizon} দিনের পূর্বাভাস` : `${horizon}-day projection`}
          subtitle={
            f.loc === "bn"
              ? "ছায়া অংশ = আস্থা ব্যাপ্তি; কমলা রেখা = নিরাপত্তা রিজার্ভ"
              : "Shaded band is the uncertainty range; the dashed line is the safety buffer."
          }
          right={
            <div className="text-right">
              <div className="text-[11px] font-semibold text-ink-400 uppercase">{copy("confidence", lang)}</div>
              <div className="tabular text-[14px] font-bold text-ink-900">{f.percent(fc.confidence, 0)}</div>
            </div>
          }
          height={320}
        >
          <ForecastChart points={fc.points} lang={f.tlang} buffer={fc.buffer} height={320} />
        </Panel>
      </div>

      <Grid cols={3} className="mb-5">
        <Panel title={f.loc === "bn" ? "দৈনিক বিভাজন" : "Day-by-day movement"} subtitle={f.loc === "bn" ? "আয় বনাম ব্যয়" : "income vs spending"} height={230}>
          <MoneyBars
            lang={f.tlang}
            height={230}
            data={fc.points.map((p) => ({ date: p.date, income: p.income, expense: p.expense }))}
            keys={[
              { key: "income", label: f.loc === "bn" ? "আয়" : "income", color: VIZ[1] },
              { key: "expense", label: f.loc === "bn" ? "ব্যয়" : "spend", color: VIZ[0] },
            ]}
          />
        </Panel>

        <Panel
          title={f.loc === "bn" ? "মডেল বনাম বেসলাইন" : "Model vs the eyeball baseline"}
          subtitle={f.loc === "bn" ? "ব্যাকটেস্টিং-এ পরিমাপ করা" : "measured by backtesting, not asserted"}
          height={230}
        >
          <div className="space-y-3">
            <Stat
              label={f.loc === "bn" ? "মডেলের গড় নির্ভুলতা (MAE)" : "Model mean absolute error"}
              value={f.taka(backtest.maeModel)}
              tone="good"
              hint={`${f.num(backtest.windows)} ${f.loc === "bn" ? "টি উইন্ডোতে" : "windows"} · ${f.pct(backtest.improvementPct, 0)} ${f.loc === "bn" ? "ভালো" : "better than baseline"}`}
            />
            <Stat label={f.loc === "bn" ? "বেসলাইন MAE" : "Baseline mean absolute error"} value={f.taka(backtest.maeBaseline)} tone="warn" />
            <div>
              <Meter
                value={backtest.maeModel}
                max={Math.max(backtest.maeBaseline, backtest.maeModel, 1)}
                tone={backtest.maeModel <= backtest.maeBaseline ? "good" : "warn"}
                label={f.loc === "bn" ? "তুলনামূলক নির্ভুলতা" : "relative accuracy"}
              />
            </div>
            <p className="text-[11.5px] leading-relaxed text-ink-500">
              {f.loc === "bn"
                ? `প্রতিটি উইন্ডোর পরে ভবিষ্যৎকে আড়াল করে মডেল চালিয়ে প্রকৃত ব্যালেন্সের সাথে মিলিয়ে দেখা হয়। MAPE: মডেল ${f.percent(backtest.mapeModel / 100, 1)} বনাম বেসলাইন ${f.percent(backtest.mapeBaseline / 100, 1)}।`
                : `Each window hides the future, runs the model, and compares against what actually happened. MAPE: model ${f.percent(backtest.mapeModel / 100, 1)} vs baseline ${f.percent(backtest.mapeBaseline / 100, 1)}.`}
            </p>
          </div>
        </Panel>

        <Panel title={f.loc === "bn" ? "মাস শেষের দৃশ্য" : "Month-end view"} subtitle={`${monthEnd.daysRemaining} ${copy("days", lang)} ${f.loc === "bn" ? "বাকি" : "remaining"}`} height={230}>
          <div className="space-y-3">
            <Stat
              label={f.loc === "bn" ? "এই মাসে এখন পর্যন্ত" : "So far this month"}
              value={f.taka(monthEnd.monthSoFar.spend)}
              hint={`${f.loc === "bn" ? "আয়" : "income"} ${f.taka(monthEnd.monthSoFar.income)}`}
            />
            <Stat
              label={f.loc === "bn" ? "মাস শেষে প্রকৃতিপত" : "Projected at month end"}
              value={f.taka(monthEnd.forecast.expectedEndingBalance)}
              tone={monthEnd.forecast.expectedEndingBalance < monthEnd.forecast.buffer ? "bad" : "good"}
              big
            />
            <div className="rounded-xl border border-ink-200 bg-ink-50 p-3">
              <div className="mb-1 text-[11px] font-bold tracking-wide text-ink-400 uppercase">
                {f.loc === "bn" ? "ঝুঁকির মাত্রা" : "Shortage risk"}
              </div>
              <div className="flex items-center gap-2">
                <Gauge className="h-4 w-4 text-ink-500" />
                <span className="text-[13px] font-bold text-ink-900 capitalize">{shortageRisk}</span>
              </div>
              <p className="mt-1 text-[11.5px] leading-relaxed text-ink-600">
                {f.loc === "bn"
                  ? `ঘাটতির সম্ভাবনা ${f.percent(shortage.lowBalanceProbability, 0)}, প্রস্তাবিত সর্বনিম্ন ব্যালেন্স ${f.taka(shortage.projectedMinBalance)}।`
                  : `${f.percent(shortage.lowBalanceProbability, 0)} probability of dipping below the buffer, with a projected low of ${f.taka(shortage.projectedMinBalance)}.`}
              </p>
              {shortage.suggestedReduction > 0 ? (
                <p className="mt-1 text-[11.5px] font-semibold text-brand-700">
                  {f.loc === "bn"
                    ? `প্রায় ${f.taka(shortage.suggestedReduction)} কমালে ঘাটতি পূরণ হবে।`
                    : `Trimming about ${f.taka(shortage.suggestedReduction)} of late-month discretionary spend closes the gap.`}
                </p>
              ) : null}
            </div>
          </div>
        </Panel>
      </Grid>

      <Card className="mb-5">
        <CardHeader
          kicker={f.loc === "bn" ? "মাসের শেষ ভাগ কেন সমস্যা" : "Why the last third of the month hurts"}
          title={f.loc === "bn" ? "ব্যয়ের কারণ ভাঙাভাঙি" : "Decomposition of the late-month spend"}
          right={<EvidenceButton evidence={shortage.evidence} />}
        />
        <Grid cols={3}>
          <Stat label={f.loc === "bn" ? "১–১০ তারিখ" : "Days 1–10"} value={f.taka(shortage.earlySpend)} />
          <Stat label={f.loc === "bn" ? "১১–২০ তারিখ" : "Days 11–20"} value={f.taka(shortage.midSpend)} />
          <Stat
            label={f.loc === "bn" ? "২১ তারিখের পর" : "After day 20"}
            value={f.taka(shortage.lateSpend)}
            tone="bad"
            hint={`${f.percent(shortage.lateShare, 0)} ${copy("total", lang).toLowerCase()}`}
          />
        </Grid>
        <div className="mt-4">
          <Table
            align="right"
            head={[
              f.loc === "bn" ? "খাত" : "Category",
              f.loc === "bn" ? "পরিমাণ" : "Amount",
              f.loc === "bn" ? "অংশ" : "Share",
              f.loc === "bn" ? "সংখ্যা" : "Transactions",
            ]}
            rows={shortage.contributors.slice(0, 8).map((c) => [
              <span className="font-semibold text-ink-800 capitalize">{c.category}</span>,
              f.taka(c.amount),
              f.percent(c.share, 0),
              f.num(c.count),
            ])}
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          kicker={copy("evidence", lang)}
          title={fc.evidence.headline}
          right={<Chip tone="neutral">{Math.round(fc.evidence.confidence * 100)}% {copy("confidence", lang)}</Chip>}
        />
        <EvidenceBody evidence={fc.evidence} />
        <div className="mt-4 flex items-start gap-2 text-[11.5px] leading-relaxed text-ink-500">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <p>
            {f.loc === "bn"
              ? `ধরণাবিধান: ${fc.evidence.assumptions.join(" ")}`
              : `Assumptions in force: ${fc.evidence.assumptions.join(" ")}`}
          </p>
        </div>
      </Card>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <Card>
          <CardHeader title={f.loc === "bn" ? "আয় আসার প্যাটার্ন" : "When income arrives"} />
          <Table
            align="right"
            head={[f.loc === "bn" ? "উৎস" : "Source", f.loc === "bn" ? "গড়" : "Average", f.loc === "bn" ? "সাধারণ দিন" : "Typical day", f.loc === "bn" ? "স্থিতিশীলতা" : "Stability"]}
            rows={bundle.sources.incomeSources.slice(0, 6).map((s) => [
              s.label,
              f.taka(s.amount / Math.max(1, s.occurrences)),
              s.typicalDay ? f.num(s.typicalDay) : "—",
              <Chip tone={s.stability >= 0.8 ? "good" : s.stability >= 0.5 ? "warn" : "bad"}>{f.percent(s.stability, 0)}</Chip>,
            ])}
          />
        </Card>
        <Card>
          <CardHeader title={f.loc === "bn" ? "আসন্ন দায়বদ্ধতা" : "Obligations inside the horizon"} />
          <Table
            align="right"
            head={[f.loc === "bn" ? "খাত" : "Item", f.loc === "bn" ? "পরিমাণ" : "Amount", f.loc === "bn" ? "দিন" : "Day", f.loc === "bn" ? "ধরন" : "Type"]}
            rows={ctx.recurring.slice(0, 7).map((r) => [
              <span className="font-semibold text-ink-800">{r.expense_name}</span>,
              f.taka(r.amount),
              f.num(r.due_day),
              r.mandatory ? (
                <Chip tone="warn">{f.loc === "bn" ? "বাধ্যতামূলক" : "mandatory"}</Chip>
              ) : (
                <Chip tone="neutral">{f.loc === "bn" ? "ঐচ্ছিক" : "optional"}</Chip>
              ),
            ])}
          />
          <p className="mt-3 text-[11.5px] leading-relaxed text-ink-500">
            {f.loc === "bn"
              ? "এই তালিকা ledger-এর সঙ্গে তুলনা করে স্বয়ংক্রিয়ভাবে শনাক্ত করা হয়েছে — অনুমান করা নয়।"
              : "This list was matched against the ledger rather than typed by hand, so the obligations priced into the forecast are the ones you actually paid."}
          </p>
        </Card>
      </div>

      <div className="mt-5">
        <Banner tone="info" icon={<TrendingDown className="h-4 w-4" />}>
          <p className="mb-1 font-semibold text-ink-800">
            {f.loc === "bn" ? "পূর্বাভাস কী, কী নয়" : "What a forecast is — and is not"}
          </p>
          <p>
            {f.loc === "bn"
              ? "এটি একটি সম্ভাবনার মডেল, ভবিষ্যদ্বাণ নয়। আয় সময়মতো না এলে, বা একটি বড় চাহিদা হঠাৎ এলে, প্রকৃত ফলাফল পার্থক্য হবে। তাই আমরা ব্যাপ্তি দেখাই এবং নিজে যাচাই করার সুযোগ দিই।"
              : "This is a probability model, not a promise. If income arrives late, or an expense lands early, the outcome will differ — which is why the band is shown and the assumptions are listed rather than hidden."}
          </p>
        </Banner>
      </div>
    </div>
  );
}