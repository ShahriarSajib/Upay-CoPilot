import { CalendarClock, Info, Repeat, Wallet as WalletIcon } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Stat, Table, cx } from "@/components/ui";
import { EvidenceBody, EvidenceButton } from "@/components/Evidence";
import { AreaTrend, Donut, Legend2, MoneyBars, Panel, VIZ } from "@/components/charts";

export default function MoneySources() {
  const bundle = useBundle();
  const f = useFmt();
  const { lang } = useCopilot();
  if (!bundle) return null;

  const { ctx, sources } = bundle;
  const liquid = sources.wallets.filter((w) => w.type !== "other_digital");
  const volatile = sources.incomeSources.filter((s) => s.stability < 0.7);

  return (
    <div>
      <PageHeader
        title={copy("sources", lang)}
        subtitle={
          f.loc === "bn"
            ? "কোথা থেকে কত আসে, কত নিয়মিত, এবং কোন ওয়ালেটে জমা আছে — ফোরকাস্ট এই তথ্য দিয়েই দৈনিক সিদ্ধান্ত নেয়।"
            : "Where money comes from, how dependable each source is, and which wallet it lands in. The forecast places income on specific dates using exactly this."
        }
      />

      <Grid cols={4} className="mb-5">
        <Card>
          <Stat
            label={f.loc === "bn" ? "আয়ের উৎস" : "Income sources"}
            value={f.num(sources.incomeSources.length)}
            big
            hint={`${f.num(ctx.incomeEvents.length)} ${f.loc === "bn" ? "টি আয়ের ঘটনা" : "income events"}`}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "গড় মাসিক আয়" : "Average monthly income"}
            value={f.taka(ctx.monthlyIncomeAvg)}
            hint={`${f.loc === "bn" ? "ঔচিত্য" : "CV"} ${f.pct(ctx.incomeCv * 100, 0)}`}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "সবচেয়ে অনিশ্চিত উৎস" : "Most variable source"}
            value={
              volatile.length ? (
                <span className="text-[16px]">{f.bi(volatile[0].label, volatile[0].labelBn)}</span>
              ) : (
                <span className="text-[16px]">{f.loc === "bn" ? "সব নিয়মিত" : "All regular"}</span>
              )
            }
            hint={
              volatile.length
                ? `${f.percent(volatile[0].stability, 0)} ${f.loc === "bn" ? "স্থিতিশীলতা" : "stability"} · CV ${f.pct(volatile[0].cv * 100, 0)}`
                : f.loc === "bn" ? "নিয়মিত আয়" : "predictable income"
            }
            tone={volatile.length ? "warn" : "good"}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "তরল ব্যালেন্স" : "Liquid balance"}
            value={f.taka(ctx.liquidBalance)}
            hint={`${f.loc === "bn" ? "upay" : "upay"} ${f.taka(ctx.upayBalance)}`}
          />
        </Card>
      </Grid>

      {volatile.length ? (
        <div className="mb-5">
          <Banner tone="warn" title={f.loc === "bn" ? "অনিয়মিত অংশের জন্য বেশি সময় দেওয়া হয়েছে" : "The uncertain part gets a wider margin"} icon={<Info className="h-4 w-4" />}>
            <p>
              {f.loc === "bn"
                ? `${volatile.map((v) => f.bi(v.label, v.labelBn)).join(", ")} — ${f.loc === "bn" ? "এই অংশের" : "these "}পরিমাণ স্থিতিশীল নয়, তাই ফোরকাস্ট এই অংশকে নির্দিষ্ট দিনে বসায় না এবং আস্থা ব্যাপ্তি চওড়া করে।`
                : `${volatile.map((v) => v.label).join(", ")} ${volatile.length === 1 ? "varies" : "vary"} significantly, so the forecast does not pin ${volatile.length === 1 ? "it" : "them"} to a specific day and widens the confidence band for that portion of income.`}
            </p>
          </Banner>
        </div>
      ) : null}

      <Grid cols={3} className="mb-5">
        <Panel
          title={f.loc === "bn" ? "উৎসভিত্তিক আয়" : "Income by source"}
          subtitle={f.loc === "bn" ? "গড় মাসিক অংশ" : "share of average month"}
          height={240}
        >
          <Donut
            data={sources.incomeSources.map((s) => ({ name: f.bi(s.label, s.labelBn), value: Math.round(s.amount) }))}
            lang={f.tlang}
            centerValue={f.compact(ctx.monthlyIncomeAvg)}
            centerLabel={f.loc === "bn" ? "মাসিক গড়" : "monthly avg"}
            height={240}
          />
          <div className="mt-2">
            <Legend2
              items={sources.incomeSources.slice(0, 5).map((s, i) => ({ label: f.bi(s.label, s.labelBn), color: VIZ[i % VIZ.length] }))}
            />
          </div>
        </Panel>

        <Panel
          title={f.loc === "bn" ? "মাসভিত্তিক আয়" : "Month-by-month income"}
          subtitle={f.loc === "bn" ? "নিয়মিত ও অনিয়মিত মিলিয়ে" : "scheduled and irregular combined"}
          height={240}
        >
          <MoneyBars
            lang={f.tlang}
            height={240}
            xKey="key"
            xTick={(v) => f.month(v)}
            data={ctx.monthly.map((m) => ({ key: m.key, income: Math.round(m.income) }))}
            keys={[{ key: "income", label: f.loc === "bn" ? "আয়" : "income", color: VIZ[1] }]}
          />
          <p className="mt-2 text-[11.5px] leading-relaxed text-ink-500">
            {f.loc === "bn"
              ? `সর্বোচ্চ ${f.taka(Math.max(...ctx.monthly.map((m) => m.income)))}, সর্বনিম্ন ${f.taka(Math.min(...ctx.monthly.map((m) => m.income)))} — গড় ${f.taka(ctx.monthlyIncomeAvg)}।`
              : `High ${f.taka(Math.max(...ctx.monthly.map((m) => m.income)))}, low ${f.taka(Math.min(...ctx.monthly.map((m) => m.income)))}, average ${f.taka(ctx.monthlyIncomeAvg)}.`}
          </p>
        </Panel>

        <Panel
          title={f.loc === "bn" ? "দৈনিক আয়ের ধরন" : "Daily income shape"}
          subtitle={f.loc === "bn" ? "সাম্প্রতিক ৯০ দিন" : "last 90 days"}
          height={240}
        >
          <AreaTrend
            data={ctx.daily.slice(-90).map((d) => ({ date: d.iso, income: Math.round(d.income) }))}
            keys={[{ key: "income", label: f.loc === "bn" ? "আয়" : "income", color: VIZ[1] }]}
            lang={f.tlang}
            height={240}
          />
        </Panel>
      </Grid>

      <Grid cols={2} className="mb-5">
        <Card>
          <CardHeader
            kicker={f.loc === "bn" ? "স্থিতিশীলতা" : "Predictability"}
            title={f.loc === "bn" ? "কোন উৎস কত নিয়মিত" : "Which source can be relied on"}
            subtitle={
              f.loc === "bn"
                ? "স্থিতিশীলতা = ১ ÷ (১ + পরিবর্তনশীলতা)। ১.০ মানে প্রায় নির্দিষ্ট পরিমাণ, ০ মানে সম্পূর্ণ অনির্দিষ্ট।"
                : "Stability is 1 ÷ (1 + coefficient of variation). 1.0 means a near-fixed amount; 0 means completely unpredictable."
            }
            right={<EvidenceButton evidence={sources.evidence} />}
          />
          <Table
            align="right"
            head={[
              f.loc === "bn" ? "উৎস" : "Source",
              f.loc === "bn" ? "মোট" : "Total",
              f.loc === "bn" ? "অংশ" : "Share",
              f.loc === "bn" ? "বার" : "Count",
              f.loc === "bn" ? "সাধারণ দিন" : "Typical day",
              f.loc === "bn" ? "স্থিতিশীলতা" : "Stability",
            ]}
            rows={sources.incomeSources.map((s) => [
              <span className="font-semibold text-ink-800">{f.bi(s.label, s.labelBn)}</span>,
              f.taka(s.amount),
              f.percent(s.share, 0),
              f.num(s.occurrences),
              <span className="inline-flex items-center gap-1">
                <CalendarClock className="h-3 w-3 text-ink-400" />
                {s.typicalDay ? `${f.num(s.typicalDay)}` : "—"}
              </span>,
              <span className="inline-flex items-center justify-end gap-2">
                <span className="hidden w-14 sm:inline-block">
                  <Meter value={s.stability * 100} tone={s.stability >= 0.7 ? "good" : s.stability >= 0.4 ? "warn" : "bad"} />
                </span>
                <span className={cx("tabular font-bold", s.stability >= 0.7 ? "text-mint-700" : "text-amber-ink")}>
                  {f.percent(s.stability, 0)}
                </span>
              </span>,
            ])}
          />
          <p className="mt-3 text-[11.5px] leading-relaxed text-ink-500">{f.bi(sources.forecastImpact, sources.forecastImpactBn)}</p>
        </Card>

        <Card>
          <CardHeader
            kicker={f.loc === "bn" ? "ওয়ালেট" : "Wallets"}
            title={f.loc === "bn" ? "টাকা কোথায় জমা আছে" : "Where the money is parked"}
            subtitle={f.loc === "bn" ? "শেষ পর্যবেক্ষিত ব্যালেন্স অনুযায়ী" : "by last observed balance"}
          />
          <Table
            align="right"
            head={[
              f.loc === "bn" ? "ওয়ালেট" : "Wallet",
              f.loc === "bn" ? "ধরন" : "Type",
              f.loc === "bn" ? "শেষ ব্যালেন্স" : "Closing",
              f.loc === "bn" ? "আসা" : "In",
              f.loc === "bn" ? "গেছে" : "Out",
              f.loc === "bn" ? "লেনদেন" : "Txns",
            ]}
            rows={sources.wallets.map((w) => [
              <span className="font-mono text-[11.5px] text-ink-600">{w.walletId}</span>,
              <Chip tone={w.type === "cash" ? "warn" : w.type === "upay" ? "brand" : "neutral"}>{w.type}</Chip>,
              <span className="tabular font-semibold text-ink-900">{f.taka(w.closing)}</span>,
              <span className="text-mint-700">{f.taka(w.inflow)}</span>,
              <span className="text-brand-700">{f.taka(w.outflow)}</span>,
              f.num(w.txCount),
            ])}
          />
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {liquid.map((w) => (
              <div key={w.walletId} className="rounded-xl border border-ink-200 px-3 py-2.5">
                <div className="flex items-center gap-1.5 text-[11px] font-bold tracking-wide text-ink-400 uppercase">
                  <WalletIcon className="h-3 w-3" />
                  {w.type}
                </div>
                <div className="tabular mt-1 text-[15px] font-bold text-ink-900">{f.taka(w.closing)}</div>
                <div className="mt-1">
                  <Meter value={w.share * 100} tone="brand" />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11.5px] leading-relaxed text-ink-500">
            {f.loc === "bn"
              ? "তরল ব্যালেন্স = upay + ব্যাংক + নগদ। অন্য ডিজিটাল ওয়ালেট ইচ্ছাকৃতভাবে বাদ, কারণ তা তাৎক্ষণিক ব্যয়ের জন্য ব্যবহৃত হয়।"
              : "Liquid balance counts upay + bank + cash. Other digital wallets are deliberately excluded because they are spend balances rather than savings."}
          </p>
        </Card>
      </Grid>

      <Card>
        <CardHeader
          kicker={f.loc === "bn" ? "আসন্ন দায়বদ্ধতা" : "Known commitments"}
          title={f.loc === "bn" ? "যা ফোরকাস্টের সাথে মিলিয়েছে" : "What the forecast has lined up"}
          subtitle={
            f.loc === "bn"
              ? "এই তালিকা লেজারের সাথে মিলিয়ে বের করা, হাতে লেখা নয় — তাই পূর্বাভাসে এগুলোই ধার করা হয়।"
              : "Matched against the ledger rather than typed in, which is why the forecast charges these amounts on these dates."
          }
          right={<Chip tone="neutral"><Repeat className="h-3 w-3" />{f.num(ctx.recurring.length)}</Chip>}
        />
        {ctx.recurring.length ? (
          <Table
            align="right"
            head={[
              f.loc === "bn" ? "খাত" : "Item",
              f.loc === "bn" ? "খরচের ধরন" : "Category",
              f.loc === "bn" ? "পরিমাণ" : "Amount",
              f.loc === "bn" ? "ধার" : "Frequency",
              f.loc === "bn" ? "পরবর্তী দিন" : "Due day",
              f.loc === "bn" ? "ধরন" : "Type",
            ]}
            rows={[...ctx.recurring]
              .sort((a, b) => a.due_day - b.due_day)
              .map((r) => [
                <span className="font-semibold text-ink-800">{r.expense_name}</span>,
                r.category,
                f.taka(r.amount),
                r.frequency,
                `${f.num(r.due_day)}`,
                r.mandatory ? (
                  <Chip tone="warn">{f.loc === "bn" ? "বাধ্যতামূলক" : "mandatory"}</Chip>
                ) : (
                  <Chip tone="neutral">{f.loc === "bn" ? "ঐচ্ছিক" : "optional"}</Chip>
                ),
              ])}
          />
        ) : (
          <p className="text-[12.5px] text-ink-500">{copy("noData", lang)}</p>
        )}
      </Card>

      <div className="mt-5">
        <Card>
          <CardHeader
            kicker={copy("evidence", lang)}
            title={sources.evidence.headline}
            right={<Chip tone="neutral">{Math.round(sources.evidence.confidence * 100)}% {copy("confidence", lang)}</Chip>}
          />
          <EvidenceBody evidence={sources.evidence} />
        </Card>
      </div>
    </div>
  );
}