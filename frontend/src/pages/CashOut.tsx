import { Banknote, Info, Wallet as WalletIcon } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Stat, Table, cx } from "@/components/ui";
import { EvidenceBody, EvidenceButton } from "@/components/Evidence";
import { AreaTrend, Legend2, Panel, VIZ } from "@/components/charts";
import { cashOutHourHistogram, cashOutTimeline } from "@/engines/cashout";
import { CATEGORY_LABELS } from "@/engines/spending";

export default function CashOut() {
  const bundle = useBundle();
  const f = useFmt();
  const { lang } = useCopilot();
  if (!bundle) return null;

  const { ctx, cashOut } = bundle;
  const timeline = cashOutTimeline(ctx);
  const hours = cashOutHourHistogram(ctx);
  const peakHour = hours.reduce((a, b) => (b.count > a.count ? b : a), hours[0] ?? { hour: 0, count: 0 });
  const chainColors = [VIZ[1], VIZ[4], VIZ[0], VIZ[3]];

  return (
    <div>
      <PageHeader
        title={copy("cashout", lang)}
        subtitle={
          f.loc === "bn"
            ? "টাকা ডিজিটাল ব্যবস্থা থেকে বের হয়ে গেলে সেটি আর হিসাবে থাকে না। কতটা, কখন এবং কোথা খরচ হিসেবে যাচ্ছে তা দেখা যাক।"
            : "Money that leaves the digital system stops being visible. This page measures how much, how soon after income, and which spending it funds — without telling you which channel to use."
        }
      />

      <Grid cols={4} className="mb-5">
        <Card>
          <Stat
            label={f.loc === "bn" ? "ব্যয়ের নগদ অংশ" : "Cash share of spending"}
            value={f.percent(cashOut.shareOfSpend, 0)}
            big
            tone={cashOut.shareOfSpend > 0.4 ? "warn" : "neutral"}
            hint={`${f.taka(cashOut.cashSettledSpend)} ${f.loc === "bn" ? "নগদ থেকে" : "settled from cash"}`}
          />
          <div className="mt-3">
            <Meter value={cashOut.shareOfSpend * 100} tone={cashOut.shareOfSpend > 0.4 ? "warn" : "brand"} />
          </div>
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "নগদে রূপান্তর" : "Converted to cash"}
            value={f.taka(cashOut.cashOutTotal)}
            hint={`${f.num(cashOut.cashOutCount)} ${f.loc === "bn" ? "বার" : "withdrawals"} · ${f.loc === "bn" ? "গড়" : "avg"} ${f.taka(cashOut.avgCashOut)}`}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "আসা টাকার তুলনায়" : "Share of money received"}
            value={f.percent(cashOut.shareOfIncoming, 0)}
            hint={f.loc === "bn" ? "নগদ বের হওয়া ÷ আয়" : "cash-out ÷ non-cash inflow"}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "আয়ের পর কত দিনে" : "Days after income"}
            value={cashOut.daysAfterIncomeMedian === null ? "—" : f.num(cashOut.daysAfterIncomeMedian, 1)}
            big
            tone={cashOut.daysAfterIncomeMedian !== null && cashOut.daysAfterIncomeMedian <= 3 ? "warn" : "neutral"}
            hint={
              f.loc === "bn"
                ? `প্রতি মাসে ${f.num(cashOut.cashOutFrequencyPerMonth, 1)} বার`
                : `${f.num(cashOut.cashOutFrequencyPerMonth, 1)} times per month · median gap to inflow`
            }
          />
        </Card>
      </Grid>

      <div className="mb-5">
        <Card>
          <CardHeader
            kicker={f.loc === "bn" ? "টাকার যাত্রা" : "Follow the money"}
            title={f.loc === "bn" ? "আয় থেকে নগদ ব্যয় পর্যন্ত" : "From income to cash spending"}
            subtitle={
              f.loc === "bn"
                ? "প্রতিটি ধাপ পরেরটির সাথে যুক্ত — তাই যোগ করলে মোট আয়ের চেয়ে বেশি হয় না।"
                : "Each step is a subset of the one before it, so the chain reconciles back to the money that actually arrived."
            }
            right={<EvidenceButton evidence={cashOut.evidence} />}
          />
          <div className="grid gap-2 sm:grid-cols-4">
            {cashOut.chain.map((step, i) => (
              <div key={step.step} className="relative rounded-xl border border-ink-200 bg-white px-3.5 py-3">
                <div className="mb-1 flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ background: chainColors[i] }} />
                  <span className="text-[11px] font-bold text-ink-700">{f.bi(step.label, step.labelBn)}</span>
                </div>
                <div className="tabular text-[17px] font-bold text-ink-900">{f.taka(step.amount)}</div>
                <div className="mt-0.5 text-[11.5px] text-ink-500">
                  {f.percent(step.share, 0)} {f.loc === "bn" ? "আসা টাকার" : "of money in"} · {f.num(step.count)}{" "}
                  {f.loc === "bn" ? "টি লেনদেন" : "tx"}
                </div>
                {i < cashOut.chain.length - 1 ? (
                  <span className="absolute top-1/2 -right-2.5 hidden h-px w-3 bg-ink-300 sm:block" />
                ) : null}
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Grid cols={3} className="mb-5">
        <Panel
          title={f.loc === "bn" ? "নগদ বের হওয়ার ধরন" : "Cash-out rhythm"}
          subtitle={f.loc === "bn" ? "সাম্প্রতিক দিনগুলোতে আয় বনাম নগদ উত্তোলন" : "income vs withdrawal, recent days"}
          height={240}
        >
          {timeline.length ? (
            <AreaTrend
              data={timeline.map((p) => ({ date: p.date, income: p.income, cashOut: p.cashOut }))}
              keys={[
                { key: "income", label: f.loc === "bn" ? "আয়" : "income", color: VIZ[1] },
                { key: "cashOut", label: f.loc === "bn" ? "নগদ বের" : "cash out", color: VIZ[0] },
              ]}
              lang={f.tlang}
              height={240}
            />
          ) : (
            <p className="text-[12.5px] text-ink-500">{copy("noData", lang)}</p>
          )}
        </Panel>

        <Panel
          title={f.loc === "bn" ? "কোন সময়ে" : "When it happens"}
          subtitle={
            peakHour.count > 0
              ? f.loc === "bn"
                ? `সবচেয়ে বেশি ${peakHour.hour}:00 টায়`
                : `peak at ${peakHour.hour}:00`
              : copy("noData", lang)
          }
          height={240}
        >
          {hours.length ? (
            <div className="flex h-full items-end gap-1">
              {hours.map((h) => {
                const share = peakHour.count > 0 ? h.count / peakHour.count : 0;
                return (
                  <div key={h.hour} className="flex-1 text-center">
                    <div className="mx-auto w-full max-w-[18px] rounded-t bg-brand-500/80" style={{ height: `${Math.max(4, share * 150)}px` }} />
                    <div className="mt-1 text-[9.5px] text-ink-400">{h.hour}</div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-[12.5px] text-ink-500">{copy("noData", lang)}</p>
          )}
          <p className="mt-2 text-[11.5px] leading-relaxed text-ink-500">
            {f.loc === "bn"
              ? "নগদ উত্তোলনের সময় আপনার আচরণের একটি অংশ — এটিই সাধারণত মাস শেষের চাপের সঙ্গে মিলে যায়।"
              : "When you withdraw is part of the pattern; it is also what tends to line up with the month-end squeeze."}
          </p>
        </Panel>

        <Panel
          title={f.loc === "bn" ? "নগদ কোথায় খরচ হয়" : "What cash funds"}
          subtitle={f.loc === "bn" ? "নগদ ওয়ালেট থেকে হওয়া ব্যয়" : "spending settled from cash wallets"}
          height={240}
        >
          {cashOut.topCashCategories.length ? (
            <div className="space-y-2.5">
              {cashOut.topCashCategories.map((c, i) => (
                <div key={c.key}>
                  <div className="mb-1 flex items-baseline justify-between gap-2">
                    <span className="text-[12px] font-semibold text-ink-800">
                      {CATEGORY_LABELS[c.key] ? f.bi(CATEGORY_LABELS[c.key].en, CATEGORY_LABELS[c.key].bn) : c.label}
                    </span>
                    <span className="tabular text-[11.5px] font-bold text-ink-700">
                      {f.taka(c.amount)} <span className="text-ink-400">{f.percent(c.share, 0)}</span>
                    </span>
                  </div>
                  <Meter value={c.share * 100} tone="muted" />
                  <span className="hidden" style={{ background: VIZ[i % VIZ.length] }} />
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[12.5px] text-ink-500">{copy("noData", lang)}</p>
          )}
          <div className="mt-3">
            <Legend2
              items={cashOut.topCashCategories.slice(0, 4).map((c, i) => ({
                label: CATEGORY_LABELS[c.key]?.en ?? c.label,
                color: VIZ[i % VIZ.length],
              }))}
            />
          </div>
        </Panel>
      </Grid>

      <Card className="mb-5">
        <CardHeader
          kicker={f.loc === "bn" ? "মাসভিত্তিক" : "Month by month"}
          title={f.loc === "bn" ? "নগদের অংশ কি বাড়ছে" : "Is the cash share growing?"}
          right={
            <Chip tone={cashOut.trend[cashOut.trend.length - 1].cashShare > 0.4 ? "warn" : "neutral"}>
              {f.loc === "bn" ? "সাম্প্রতিক" : "latest"} {f.percent(cashOut.trend[cashOut.trend.length - 1].cashShare, 0)}
            </Chip>
          }
        />
        <Table
          align="right"
          head={[
            f.loc === "bn" ? "মাস" : "Month",
            f.loc === "bn" ? "মোট ব্যয়" : "Spend",
            f.loc === "bn" ? "নগদ থেকে" : "From cash",
            f.loc === "bn" ? "নগদের অংশ" : "Cash share",
          ]}
          rows={ctx.monthly.map((m) => [
            f.month(m.key),
            f.taka(m.spend),
            f.taka(m.cashSpend),
            <span className={cx("tabular font-semibold", m.cashShare > 0.4 ? "text-brand-700" : "text-ink-800")}>
              {f.percent(m.cashShare, 0)}
            </span>,
          ])}
        />
      </Card>

      <Grid cols={2} className="mb-5">
        <Banner tone={cashOut.shareOfSpend > 0.4 ? "warn" : "info"} title={f.loc === "bn" ? "দৃশ্যমানতার বিষয়টা" : "The real cost is visibility"} icon={<Info className="h-4 w-4" />}>
          <p>
            {f.loc === "bn"
              ? `নগদের ${f.percent(cashOut.shareOfSpend, 0)} ব্যয় ফোরকাস্ট, অস্বাভাবিক শনাক্তকরণ ও লক্ষ্য পরিকল্পনার চোখের বাইরে থাকে। এর মানে নগদ ব্যবহার নিষিদ্ধ — মানে হলো সিদ্ধান্তের সময় আপনার কাছে কম তথ্য থাকে।`
              : `${f.percent(cashOut.shareOfSpend, 0)} of consumption is invisible to the forecast, the anomaly detector and the goal planner. That is not a prohibition — it simply means fewer inputs when a decision matters.`}
          </p>
        </Banner>
        <Banner tone="neutral" title={f.loc === "bn" ? "আমরা কী করি না" : "What we deliberately do not do"} icon={<WalletIcon className="h-4 w-4" />}>
          <p>
            {f.loc === "bn"
              ? "আমরা কোন চ্যানেল ব্যবহার করতে হবে তা বলি না, এবং নগদ ব্যবহারের জন্য কোনো শাস্তি বা নিয়ম থেকে না। এটি একটি লেজার-ভিত্তিক পর্যবেক্ষণ।"
              : "No channel is prescribed, and no channel is penalised. This page reports what the ledger shows; the choice of how you pay stays entirely yours."}
          </p>
        </Banner>
      </Grid>

      <Card>
        <CardHeader
          kicker={copy("evidence", lang)}
          title={cashOut.evidence.headline}
          right={
            <Chip tone="neutral">
              <Banknote className="h-3 w-3" />
              {Math.round(cashOut.evidence.confidence * 100)}% {copy("confidence", lang)}
            </Chip>
          }
        />
        <EvidenceBody evidence={cashOut.evidence} />
      </Card>
    </div>
  );
}