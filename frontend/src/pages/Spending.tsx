import { useState } from "react";
import { AlertTriangle, Repeat, TrendingDown, TrendingUp } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Segmented, Stat, Table, cx } from "@/components/ui";
import { EvidenceBody, EvidenceButton } from "@/components/Evidence";
import { Donut, Legend2, MoneyBars, Panel, VIZ } from "@/components/charts";
import { CATEGORY_LABELS, runSpendingEngine } from "@/engines/spending";

export default function Spending() {
  const bundle = useBundle();
  const f = useFmt();
  const { lang } = useCopilot();
  const [monthKey, setMonthKey] = useState<string>(bundle ? bundle.spending.monthKey : "");

  if (!bundle) return null;
  const { ctx } = bundle;
  const monthIndex = Math.max(0, ctx.monthly.findIndex((m) => m.key === monthKey));
  const engine = monthIndex === ctx.monthly.length - 1 ? bundle.spending : runSpendingEngine(ctx, monthIndex);
  const prev = ctx.monthly[monthIndex - 1];
  const catColors = VIZ;

  return (
    <div>
      <PageHeader
        title={copy("spending", lang)}
        subtitle={
          f.loc === "bn"
            ? "খরচের শুধু পরিমাণ নয় — কখন, কোথায় এবং কতটা বদলানো যায় তাও দেখানো হচ্ছে।"
            : "Not just how much. Where it went, when in the month it happened, and how much of it you can actually change."
        }
        actions={
          <Segmented
            value={monthKey}
            onChange={setMonthKey}
            options={ctx.monthly.slice(-6).map((m) => ({ value: m.key, label: f.month(m.key) }))}
          />
        }
      />

      <Grid cols={4} className="mb-5">
        <Card>
          <Stat label={f.loc === "bn" ? "মোট ব্যয়" : "Total spending"} value={f.taka(engine.totalSpend)} big hint={`${f.num(engine.txCount)} ${f.loc === "bn" ? "টি লেনদেন" : "transactions"}`} />
        </Card>
        <Card>
          <Stat
            label={copy("essential", lang)}
            value={f.taka(engine.essentialSpend)}
            hint={`${f.percent(engine.totalSpend > 0 ? engine.essentialSpend / engine.totalSpend : 0, 0)} ${copy("total", lang).toLowerCase()}`}
          />
        </Card>
        <Card>
          <Stat
            label={copy("discretionary", lang)}
            value={f.taka(engine.discretionarySpend)}
            tone={engine.discretionaryShare > 0.4 ? "warn" : "neutral"}
            hint={`${f.percent(engine.discretionaryShare, 0)} ${copy("total", lang).toLowerCase()} · ${f.loc === "bn" ? "এখানেই সম্ভাব্য সাশ্রয়" : "the adjustable part"}`}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "২৩ তারিখের পরে ব্যয়" : "Spend after day 23"}
            value={f.percent(engine.dayProfile.lateShare, 0)}
            tone={engine.dayProfile.lateShare > 0.4 ? "bad" : engine.dayProfile.lateShare > 0.25 ? "warn" : "good"}
            hint={`${f.loc === "bn" ? "সবচেয়ে ভারী দিন" : "peak day"} ${engine.dayProfile.peakDay || "—"}`}
          />
        </Card>
      </Grid>

      {engine.dayProfile.lateShare > 0.4 ? (
        <div className="mb-5">
          <Banner tone="warn" title={f.loc === "bn" ? "মাসের শেষ ভাগেই জমা হচ্ছে খরচ" : "Spending is back-loaded into the last third of the month"} icon={<AlertTriangle className="h-4 w-4" />}>
            <p>
              {f.loc === "bn"
                ? `${f.percent(engine.dayProfile.lateShare, 0)} ব্যয় ২১ তারিখের পরে হয় — আয়ের সাথে এর তুলনা ${f.num(engine.dayProfile.lateVsEarlyRatio, 1)} গুণ।`
                : `${f.percent(engine.dayProfile.lateShare, 0)} of the month's spending happens after day 20, which is ${f.num(engine.dayProfile.lateVsEarlyRatio, 1)}× the early-month rate. That shape is what produces month-end shortage.`}
            </p>
          </Banner>
        </div>
      ) : null}

      <Grid cols={3} className="mb-5">
        <Panel
          title={f.loc === "bn" ? "কোথায় যাচ্ছে" : "Where the money went"}
          subtitle={`${f.month(monthKey)} · ${f.num(engine.categories.length)} ${f.loc === "bn" ? "টি খাত" : "categories"}`}
          height={250}
        >
          <Donut
            data={engine.categories.slice(0, 7).map((c) => ({ name: f.bi(c.label, c.labelBn), value: c.amount }))}
            lang={f.tlang}
            centerValue={f.compact(engine.totalSpend)}
            centerLabel={f.month(monthKey)}
          />
          <div className="mt-2">
            <Legend2 items={engine.categories.slice(0, 7).map((c, i) => ({ label: f.bi(c.label, c.labelBn), color: catColors[i % catColors.length] }))} />
          </div>
        </Panel>

        <Panel
          title={f.loc === "bn" ? "মাসের তিন ভাগে" : "Early vs middle vs late"}
          subtitle={f.loc === "bn" ? "কোন সময়ে খরচ জমা হচ্ছে" : "when in the month the pressure builds"}
          height={250}
        >
          <MoneyBars
            lang={f.tlang}
            height={250}
            xKey="label"
            data={engine.dayProfile.buckets.map((b) => ({ label: b.label, amount: Math.round(b.amount) }))}
            keys={[{ key: "amount", label: f.loc === "bn" ? "ব্যয়" : "spend", color: VIZ[0] }]}
          />
        </Panel>

        <Panel
          title={f.loc === "bn" ? "ছোট কিনাকাটার ফাঁদ" : "The small-purchase leak"}
          subtitle={
            f.loc === "bn"
              ? `৳${f.num(engine.smallPurchases.threshold)} বা তার কম লেনদেন`
              : `every transaction at or below ৳${f.num(engine.smallPurchases.threshold)}`
          }
          height={250}
        >
          <Stat
            label={f.loc === "bn" ? "এই ধরনের ব্যয়" : "Total in small tickets"}
            value={f.taka(engine.smallPurchases.amount)}
            big
            tone={engine.smallPurchases.shareOfSpend > 0.15 ? "warn" : "neutral"}
            hint={`${f.percent(engine.smallPurchases.shareOfSpend, 0)} ${copy("ofSpend", lang)} · ${f.num(engine.smallPurchases.count)} ${f.loc === "bn" ? "টি" : "tickets"}`}
          />
          <div className="mt-3">
            <Meter value={engine.smallPurchases.shareOfSpend * 100} tone="warn" />
          </div>
          <ul className="mt-3 space-y-1.5">
            {engine.smallPurchases.topCategories.slice(0, 4).map((c) => (
              <li key={c.key} className="flex items-baseline justify-between gap-2 text-[12px]">
                <span className="truncate text-ink-600">
                  {CATEGORY_LABELS[c.key] ? f.bi(CATEGORY_LABELS[c.key].en, CATEGORY_LABELS[c.key].bn) : c.label}
                </span>
                <span className="tabular shrink-0 font-semibold text-ink-800">
                  {f.taka(c.amount)} <span className="text-ink-400">× {f.num(c.count)}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11.5px] leading-relaxed text-ink-500">{f.bi(engine.smallPurchases.note, engine.smallPurchases.noteBn)}</p>
        </Panel>
      </Grid>

      <Grid cols={2} className="mb-5">
        <Card>
          <CardHeader
            kicker={f.loc === "bn" ? "শ্রেণিভিত্তিক" : "By category"}
            title={f.loc === "bn" ? "কোন খাত, কত, আগের মাসের তুলনায়" : "Category, amount, and the change"}
            right={<EvidenceButton evidence={engine.evidence} />}
          />
          <Table
            align="right"
            head={[
              f.loc === "bn" ? "খাত" : "Category",
              f.loc === "bn" ? "পরিমাণ" : "Amount",
              f.loc === "bn" ? "অংশ" : "Share",
              f.loc === "bn" ? "গড় টিকিট" : "Avg ticket",
              f.loc === "bn" ? "পরিবর্তন" : "Change",
              f.loc === "bn" ? "প্রয়োজনীয়তা" : "Essentiality",
            ]}
            rows={engine.categories.map((c) => [
              <span key={c.key} className="font-semibold text-ink-800">{f.bi(c.label, c.labelBn)}</span>,
              f.taka(c.amount),
              <span className="inline-flex items-center justify-end gap-2">
                <span className="hidden w-16 sm:inline-block">
                  <Meter value={c.share * 100} tone="muted" />
                </span>
                {f.percent(c.share, 0)}
              </span>,
              f.taka(c.avgTicket),
              c.vsLastMonth === null ? (
                <span className="text-ink-300">—</span>
              ) : (
                <span className={cx("tabular inline-flex items-center gap-1 font-semibold", c.vsLastMonth > 0 ? "text-brand-700" : "text-mint-700")}>
                  {c.vsLastMonth > 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                  {f.percent(c.vsLastMonth, 0)}
                </span>
              ),
              <Chip tone={c.essentialShare >= 0.65 ? "good" : c.essentialShare >= 0.3 ? "warn" : "bad"}>
                {c.essentialShare >= 0.65
                  ? f.loc === "bn" ? "প্রয়োজনীয়" : "essential"
                  : c.essentialShare >= 0.3
                    ? f.loc === "bn" ? "মিশ্র" : "mixed"
                    : f.loc === "bn" ? "ঐচ্ছিক" : "optional"}
              </Chip>,
            ])}
          />
          <p className="mt-3 text-[11.5px] leading-relaxed text-ink-500">
            {f.loc === "bn"
              ? `প্রয়োজনীয়তা প্রতিটি খাতের জন্য নির্ধারিত স্থির অনুমান — ${f.month(monthKey)} থেকে বের করা নয়, তবে প্রতিটি কেন এভাবে বাছা হয়েছে তা প্রমাণে দেখানো আছে।`
              : `Essentiality is a fixed household assumption per category, not fitted to this customer — the exact share and its justification are in the evidence panel.`}
          </p>
        </Card>

        <Card>
          <CardHeader
            kicker={f.loc === "bn" ? "আবিষ্কৃত" : "Detected from the ledger"}
            title={f.loc === "bn" ? "নিয়মিত বাইল ও দায়বদ্ধতা" : "Recurring bills, found automatically"}
            subtitle={
              f.loc === "bn"
                ? "প্রতি মাসে একই ক্যাটাগরি ও প্রায় একই পরিমাণ — স্বয়ংক্রিয়ভাবে শনাক্ত।"
                : "Same category, near-identical amount, repeating cadence — detected, not typed in."
            }
          />
          {engine.recurring.length ? (
            <Table
              align="right"
              head={[
                f.loc === "bn" ? "খাত" : "Item",
                f.loc === "bn" ? "পরিমাণ" : "Amount",
                f.loc === "bn" ? "ধরন" : "Cadence",
                f.loc === "bn" ? "বার" : "Seen",
                f.loc === "bn" ? "দিন" : "Day",
                f.loc === "bn" ? "আস্থা" : "Confidence",
              ]}
              rows={engine.recurring.map((r) => [
                <span className="flex items-center gap-1.5 font-semibold text-ink-800">
                  <Repeat className="h-3 w-3 text-ink-400" />
                  {r.label}
                </span>,
                f.taka(r.amount),
                f.loc === "bn"
                  ? { monthly: "মাসিক", weekly: "সাপ্তাহিক", fortnightly: "পাক্ষিক" }[r.frequency]
                  : r.frequency,
                f.num(r.occurrences),
                f.num(r.expectedDay),
                <Chip tone={r.confidence >= 0.7 ? "good" : "warn"}>{f.percent(r.confidence, 0)}</Chip>,
              ])}
            />
          ) : (
            <p className="text-[12.5px] text-ink-500">{copy("noData", lang)}</p>
          )}
          {prev ? (
            <p className="mt-3 text-[11.5px] text-ink-500">
              {f.loc === "bn"
                ? `${f.month(prev.key)}-এ মোট ব্যয় ছিল ${f.taka(prev.spend)}, ${f.month(monthKey)}-এ ${f.taka(engine.totalSpend)}।`
                : `${f.month(prev.key)} total was ${f.taka(prev.spend)}; ${f.month(monthKey)} is ${f.taka(engine.totalSpend)}.`}
            </p>
          ) : null}
        </Card>
      </Grid>

      <Card>
        <CardHeader
          kicker={copy("evidence", lang)}
          title={engine.evidence.headline}
          right={<Chip tone="neutral">{Math.round(engine.evidence.confidence * 100)}% {copy("confidence", lang)}</Chip>}
        />
        <EvidenceBody evidence={engine.evidence} />
      </Card>
    </div>
  );
}