import { useState } from "react";
import { Calculator, Info, Scale, ShieldAlert, ShieldCheck } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Segmented, Stat, Table, cx } from "@/components/ui";
import { EvidenceBody, EvidenceButton, ResponsibleNotice } from "@/components/Evidence";
import { Panel, VIZ } from "@/components/charts";
import {
  READINESS_BANDS,
  READINESS_BANDS_BN,
  READINESS_DISCLAIMER,
  READINESS_DISCLAIMER_BN,
} from "@/engines/credit";
import { loanAffordability } from "@/engines/simulator";

const TERM_SETS: { label: string; months: number[] }[] = [
  { label: "6 / 12", months: [6, 12] },
  { label: "12 / 24", months: [12, 24] },
  { label: "24 / 36", months: [24, 36] },
];

export default function CreditReadiness() {
  const bundle = useBundle();
  const f = useFmt();
  const { lang } = useCopilot();
  const [termSet, setTermSet] = useState<string>("12 / 24");
  const [amount, setAmount] = useState<string>("5000");

  if (!bundle) return null;
  const { ctx, readiness } = bundle;
  const terms = TERM_SETS.find((t) => t.label === termSet)?.months ?? [12, 24];
  const parsed = Number(amount) || 0;
  const rows = parsed > 0 ? loanAffordability(ctx, [parsed], terms) : [];
  const affordable = rows.filter((r) => r.remainingMonthlyCash > 0);
  const surplus = readiness.evidence.metrics.find((m) => m.id === "surplus");

  return (
    <div>
      <PageHeader
        title={copy("credit", lang)}
        subtitle={
          f.loc === "bn"
            ? "এটি আপনার টাকা চলার ধরনের বর্ণনা — ঋণযোগ্যতার সিদ্ধান্ত নয়। এখানে কোনো অনুমোদন বা প্রত্যাখ্যানের সিদ্ধান্ত নেই এবং থাকবেও না।"
            : "This describes the shape of your cash flow. It is not a lending decision, and no approve/decline path exists anywhere in this product."
        }
        actions={<Chip tone="warn"><ShieldAlert className="h-3 w-3" />{f.loc === "bn" ? "তথ্যমূলক" : "informational"}</Chip>}
      />

      <div className="mb-5">
        <ResponsibleNotice icon={<ShieldAlert className="h-4 w-4" />}>
          <p className="font-semibold text-ink-800">
            {f.loc === "bn" ? READINESS_DISCLAIMER_BN : READINESS_DISCLAIMER}
          </p>
          <p className="mt-1 text-ink-500">
            {f.loc === "bn"
              ? "কোনো ব্যাংক, প্রতিষ্ঠান বা নিয়ন্ত্রক সংস্থার কাছে এই স্কোর যায় না। এটি শুধু আপনার নিজের কাছে ব্যাখ্যা করার জন্য তৈরি।"
              : "No bank, institution or regulator receives this score. It exists so you can understand your own position, nothing more."}
          </p>
        </ResponsibleNotice>
      </div>

      <Grid cols={4} className="mb-5">
        <Card>
          <div className="text-[11px] font-semibold tracking-wide text-ink-400 uppercase">
            {f.loc === "bn" ? "ধরন" : "Pattern"}
          </div>
          <div className="mt-1 text-[18px] leading-tight font-bold text-ink-900">
            {f.bi(READINESS_BANDS[readiness.band], READINESS_BANDS_BN[readiness.band])}
          </div>
          <div className="mt-3">
            <Meter
              value={readiness.dimensions.reduce((a, d) => a + d.contribution, 0)}
              tone={readiness.band === "strong" || readiness.band === "good" ? "good" : readiness.band === "critical" ? "bad" : "warn"}
            />
          </div>
          <p className="mt-3 text-[11.5px] leading-relaxed text-ink-500">{f.loc === "bn" ? "এটি একটি ধরনের বর্ণনা, সংখ্যা স্কোর নয়।" : "This is a description of a pattern, not a number you are graded on."}</p>
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "গড় মাসিক অতিশেষ" : "Average monthly surplus"}
            value={f.taka(Number(surplus?.value ?? 0))}
            big
            tone={Number(surplus?.value ?? 0) > 0 ? "good" : "bad"}
            hint={f.loc === "bn" ? "যা থেকে কিস্তি বসতে হয়" : "what an instalment has to fit inside"}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "মাসিক দায়বদ্ধতা" : "Monthly commitments"}
            value={f.taka(readiness.monthlyObligation)}
            hint={`${f.num(readiness.obligations.length)} ${f.loc === "bn" ? "টি ধার" : "recurring obligations"}`}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "বাধ্যতামূলক দায়" : "Mandatory obligations"}
            value={f.taka(readiness.obligations.filter((o) => o.mandatory).reduce((a, o) => a + o.amount, 0))}
            hint={`${f.num(readiness.obligations.filter((o) => o.mandatory).length)} ${f.loc === "bn" ? "টি বাধ্যতামূলক" : "mandatory"}`}
          />
        </Card>
      </Grid>

      <Grid cols={2} className="mb-5">
        <Card>
          <CardHeader
            kicker={f.loc === "bn" ? "ভিত্তি" : "Basis"}
            title={f.loc === "bn" ? "কোন মাপগুলো এই ধরনটি তৈরি করেছে" : "What builds this pattern"}
            right={<EvidenceButton evidence={readiness.evidence} />}
          />
          <div className="space-y-2.5">
            {readiness.dimensions.map((d) => (
              <div key={d.key}>
                <div className="mb-1 flex items-baseline justify-between gap-3">
                  <span className="truncate text-[12.5px] font-semibold text-ink-800">{f.bi(d.label, d.labelBn)}</span>
                  <span className="tabular shrink-0 text-[11.5px] font-bold text-ink-600">
                    {f.num(d.value)}/100 · {d.contribution >= 0 ? "+" : ""}
                    {f.num(d.contribution, 1)}
                  </span>
                </div>
                <Meter value={d.value} tone={d.value >= 65 ? "good" : d.value >= 45 ? "warn" : "bad"} />
                <p className="mt-1 text-[11.5px] leading-snug text-ink-500">{d.detail}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <div className="rounded-xl border border-mint-100 bg-mint-50/50 px-3 py-2">
              <div className="mb-1 text-[11px] font-bold tracking-wide text-mint-700 uppercase">
                {f.loc === "bn" ? "শক্তি" : "Strengths"}
              </div>
              <ul className="space-y-1">
                {readiness.strengths.map((d) => (
                  <li key={d.key} className="text-[11.5px] text-ink-600">
                    {f.bi(d.label, d.labelBn)} <span className="tabular font-bold text-mint-700">{f.num(d.value)}</span>
                  </li>
                ))}
                {!readiness.strengths.length ? (
                  <li className="text-[11.5px] text-ink-500">{copy("noData", lang)}</li>
                ) : null}
              </ul>
            </div>
            <div className="rounded-xl border border-amber-100 bg-amber-50/40 px-3 py-2">
              <div className="mb-1 text-[11px] font-bold tracking-wide text-amber-ink uppercase">
                {f.loc === "bn" ? "মনোযোগ" : "Attention"}
              </div>
              <ul className="space-y-1">
                {readiness.attention.map((d) => (
                  <li key={d.key} className="text-[11.5px] text-ink-600">
                    {f.bi(d.label, d.labelBn)} <span className="tabular font-bold text-amber-ink">{f.num(d.value)}</span>
                  </li>
                ))}
                {!readiness.attention.length ? (
                  <li className="text-[11.5px] text-ink-500">
                    {f.loc === "bn" ? "কোনো মাত্রাই দুর্বল নয়।" : "No weak dimension."}
                  </li>
                ) : null}
              </ul>
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          <Panel
            title={f.loc === "bn" ? "অনুমানমূলক অ্যাফোর্ডেবিলিটি" : "Hypothetical affordability"}
            subtitle={
              f.loc === "bn"
                ? "প্রশ্ন: এই কিস্তি আপনার অতিশেষের মধ্যে ঢুকবে কি না — কোনো অনুমোদন নয়, শুধু হিসাব।"
                : "The question is whether a payment would fit inside your surplus. It models nothing real and approves nothing."
            }
            height={200}
          >
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2">
                <span className="text-[12px] font-semibold text-ink-600">
                  {f.loc === "bn" ? "পরিমাণ" : "Amount"}
                </span>
                <input
                  type="number"
                  min={0}
                  step={500}
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-28 rounded-lg border border-ink-200 px-2.5 py-1.5 text-[13px] font-semibold text-ink-900"
                />
              </label>
              <Segmented value={termSet} onChange={setTermSet} options={TERM_SETS.map((t) => ({ value: t.label, label: `${t.label} ${f.loc === "bn" ? "মাস" : "mo"}` }))} />
            </div>
            {rows.length ? (
              <Table
                align="right"
                head={[
                  f.loc === "bn" ? "মেয়াদ" : "Term",
                  f.loc === "bn" ? "মাসিক কিস্তি" : "Monthly payment",
                  f.loc === "bn" ? "গড় অতিশেষের পর" : "After surplus",
                  f.loc === "bn" ? "রিজার্ভ" : "Buffer",
                ]}
                rows={rows.map((r) => [
                  `${f.num(r.months)} ${f.loc === "bn" ? "মাস" : "mo"}`,
                  f.taka(r.monthlyPayment),
                  <span className={cx("tabular font-semibold", r.remainingMonthlyCash > 0 ? "text-mint-700" : "text-brand-700")}>
                    {f.taka(r.remainingMonthlyCash)}
                  </span>,
                  r.bufferRetained ? (
                    <Chip tone="good">{f.loc === "bn" ? "অক্ষত" : "retained"}</Chip>
                  ) : (
                    <Chip tone="bad">{f.loc === "bn" ? "আক্রান্ত" : "consumed"}</Chip>
                  ),
                ])}
              />
            ) : (
              <p className="text-[12.5px] text-ink-500">
                {f.loc === "bn" ? "একটি পরিমাণ লিখুন।" : "Enter an amount to model."}
              </p>
            )}
          </Panel>

          <Card>
            <CardHeader
              kicker={f.loc === "bn" ? "সীমাবদ্ধতা" : "Limits of this tool"}
              title={f.loc === "bn" ? "যা এখানে বলা হচ্ছে না" : "What this does not tell you"}
            />
            <ul className="space-y-1.5">
              {[
                {
                  en: "Whether you would be approved — no approval logic exists in this product.",
                  bn: "আপনি অনুমোদন পাবেন কি না — এই পণ্যে অনুমোদনের কোনো যুক্তি নেই।",
                },
                {
                  en: "What rate you would actually be offered — the 12% used here is an illustrative constant.",
                  bn: "আপনি প্রকৃতে কোন হার পাবেন — এখানে ব্যবহৃত ১২% একটি উদাহরণমূলক ধ্রুবপরিমাণ।",
                },
                {
                  en: "Interest rates, fees or credit-scoring criteria used by any real lender.",
                  bn: "সুদের হার, ফি বা কোনো প্রকৃত ঋণদাতার স্কোরিং নিয়ম।",
                },
                {
                  en: "Whether borrowing is a good idea — that depends on your own plans, not this model.",
                  bn: "ঋণ নেওয়া ভালো হবে কি না — তা আপনার পরিকল্পনার উপর নির্ভর করে, এই মডেলের উপর নয়।",
                },
              ].map((line, i) => (
                <li key={i} className="flex items-start gap-2 text-[12px] leading-relaxed text-ink-600">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-300" />
                  {f.bi(line.en, line.bn)}
                </li>
              ))}
            </ul>
            {affordable.length ? (
              <p className="mt-3 flex items-start gap-2 text-[11.5px] leading-relaxed text-mint-700">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {f.loc === "bn"
                  ? `${f.taka(parsed)} নিয়ে ${affordable.length} টি মেয়াদ অনুমানমূলকভাবে আপনার অতিশেষের মধ্যে ঢুকে যায়। এটি কোনো অনুমোদন নয়।`
                  : `At ${f.taka(parsed)}, ${affordable.length} term(s) would hypothetically fit inside your surplus. That is an arithmetic observation, not an approval.`}
              </p>
            ) : null}
          </Card>
        </div>
      </Grid>

      <Card className="mb-5">
        <CardHeader
          kicker={f.loc === "bn" ? "আপনার দায়বদ্ধতার চিত্র" : "Your obligation picture"}
          title={f.loc === "bn" ? "ফোরকাস্টে যা ধার করা হয়েছে" : "What the forecast already charges"}
          subtitle={
            f.loc === "bn"
              ? "এই তালিকা ছাড়া কোনো কিস্তির কথা বলা যাবে না — তাই এটি আগে দেখে নেওয়া ভালো।"
              : "Any future instalment would have to sit alongside these, which is why they are shown first."
          }
        />
        <Table
          align="right"
          head={[
            f.loc === "bn" ? "দায়" : "Obligation",
            f.loc === "bn" ? "পরিমাণ" : "Amount",
            f.loc === "bn" ? "প্রতি মাসের তারিখ" : "Day of month",
            f.loc === "bn" ? "ধরন" : "Type",
            f.loc === "bn" ? "আয়ের অনুপাত" : "Share of income",
          ]}
          rows={readiness.obligations.map((o) => [
            <span className="font-semibold text-ink-800">{o.name}</span>,
            f.taka(o.amount),
            `${f.num(o.dueDay)}`,
            o.mandatory ? (
              <Chip tone="warn">{f.loc === "bn" ? "বাধ্যতামূলক" : "mandatory"}</Chip>
            ) : (
              <Chip tone="neutral">{f.loc === "bn" ? "ঐচ্ছিক" : "optional"}</Chip>
            ),
            f.percent(ctx.monthlyIncomeAvg > 0 ? o.amount / ctx.monthlyIncomeAvg : 0, 1),
          ])}
        />
      </Card>

      <Grid cols={2} className="mb-5">
        <Banner tone="neutral" title={f.loc === "bn" ? "কোনো প্রতিষ্ঠান এই তথ্য পায় না" : "No institution receives this"} icon={<Scale className="h-4 w-4" />}>
          <p>
            {f.loc === "bn"
              ? "এই পণ্যের কোনো অংশই কোনো ঋণদাতার কাছে ডেটা পাঠায় না। বাস্তবে ঋণের আবেদন হলে আলাদা, সম্পূর্ণ ভিন্ন প্রক্রিয়া — এখানে যা আছে তা কেবল আপনার নিজের হিসাব।"
              : "Nothing in this product transmits anything to a lender. A real application is a separate process with different data; what is here is your own arithmetic."}
          </p>
        </Banner>
        <Banner tone="info" title={f.loc === "bn" ? "কেন এই পর্দাটি রাখা হয়েছে" : "Why this screen keeps saying no"} icon={<Calculator className="h-4 w-4" />}>
          <p>
            {f.loc === "bn"
              ? "কারণ আর্থিক শিক্ষার সরঞ্জাম হিসেবে দায়িত্বের সীমা স্পষ্ট থাকা দরকার। বিশ্বাসযোগ্যতা এখানে সত্যকে বলার সাহস থেকেই শুরু হয়।"
              : "Because a financial-literature tool is only credible if its limits are visible. Trust starts with stating plainly what the tool cannot do."}
          </p>
        </Banner>
      </Grid>

      <Card>
        <CardHeader
          kicker={copy("evidence", lang)}
          title={readiness.evidence.headline}
          right={
            <Chip tone="neutral">
              <Info className="h-3 w-3" />
              {Math.round(readiness.evidence.confidence * 100)}% {copy("confidence", lang)}
            </Chip>
          }
        />
        <EvidenceBody evidence={readiness.evidence} />
        <p className="mt-4 text-[11.5px] leading-relaxed text-ink-500">
          <span className="inline-block h-2 w-2 rounded-full align-middle" style={{ background: VIZ[3] }} />{" "}
          {f.loc === "bn"
            ? "সুদের হার ১২% একটি উদাহরণমূলক ধ্রুবপরিমাণ, কোনো প্রকৃত উদ্ধতি নয়। প্রতিটি ফলাফল শুধুমাত্র গাণিতিক হিসাব।"
            : "The 12% annual rate is an illustrative constant, not a quoted offer. Every figure here is arithmetic on your own history."}
        </p>
      </Card>
    </div>
  );
}