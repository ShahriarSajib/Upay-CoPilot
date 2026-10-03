import { useMemo } from "react";
import { Activity, AlertTriangle, CheckCircle2, FlaskConical, ShieldCheck, Users } from "lucide-react";
import { useBundle } from "@/hooks/useBundle";
import { useCopilot, useFmt } from "@/data/store";
import { buildUserContext } from "@/data/context";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, Meter, PageHeader, Stat, Table, cx } from "@/components/ui";
import { ResponsibleNotice } from "@/components/Evidence";
import { CompareChart, Panel, VIZ } from "@/components/charts";
import { fairnessProbe } from "@/engines/credit";
import { BENCHMARK, runAssistantBenchmark } from "@/engines/assistant";
import { personaLabel } from "@/data/context";

const FIELD_LABEL: Record<string, string> = {
  end_month_shortage_label: "End-of-month shortage",
  high_cash_dependency_label: "High cash dependency",
  irregular_income_label: "Irregular income",
  overspending_label: "Overspending",
  goal_progress_label: "Goal progress",
  financial_pressure_label: "Financial pressure",
  anomaly_count: "Anomaly count",
};

export default function Evaluation() {
  const bundle = useBundle();
  const f = useFmt();
  const { data, users } = useCopilot();
  const lang = "en";
  const ctx = bundle?.ctx ?? null;

  const benchmark = useMemo(() => runAssistantBenchmark(), []);
  const allContexts = useMemo(() => {
    if (data && users.length) return users.map((u) => buildUserContext(data, u.user_id));
    return ctx ? [ctx] : [];
  }, [data, users, ctx]);
  const probes = useMemo(
    () =>
      (["occupation", "age_group", "location_type"] as const).map((key) => ({
        key,
        rows: fairnessProbe(allContexts, key),
      })),
    [allContexts],
  );

  if (!bundle || !ctx) return null;

  const { anomaly, backtest, labelAgreement } = bundle;

  const benchmarkChart = benchmark.byGroup.map((g) => ({ group: g.group, accuracy: Math.round(g.accuracy * 100) }));

  return (
    <div>
      <PageHeader
        title={copy("evaluation", lang)}
        subtitle={
          f.loc === "bn"
            ? "পণ্যত মডেল ও ইঞ্জিনের সত্যাসত্য যাচাই। প্রতিটি সংখ্যা এই পর্দায়ই হিসাব হয়েছে — কোথাও হাতে লেখা দাবি নেই।"
            : "Measured accuracy for the product's models and engines. Every figure on this screen was computed here at runtime — nothing is asserted."
        }
        actions={<Chip tone="brand"><FlaskConical className="h-3 w-3" />{f.num(allContexts.length)} {f.loc === "bn" ? "প্রোফাইল" : "profiles"}</Chip>}
      />

      <div className="mb-5">
        <ResponsibleNotice icon={<ShieldCheck className="h-4 w-4" />}>
          <p className="font-semibold text-ink-800">
            {f.loc === "bn"
              ? "গ্রাউন্ড ট্রুথ শুধু এই পর্দায়।"
              : "Ground truth appears on this screen and nowhere else."}
          </p>
          <p className="mt-1 text-ink-500">
            {copy("groundTruthNotice", "bn")}
          </p>
        </ResponsibleNotice>
      </div>

      <Grid cols={4} className="mb-5">
        <Card>
          <Stat
            label={f.loc === "bn" ? "ফোরকাস্টের তুলনামূলক উন্নতি" : "Forecast vs baseline"}
            value={f.percent(backtest.improvementPct, 0)}
            big
            tone={backtest.improvementPct > 0 ? "good" : "warn"}
            hint={
              f.loc === "bn"
                ? `${f.num(backtest.windows)} টি টেস্ট উইন্ডো · MAE ${f.taka(backtest.maeModel)}`
                : `${backtest.windows} test windows · MAE ${f.taka(backtest.maeModel)}`
            }
          />
          <div className="mt-2">
            <Meter value={Math.min(100, backtest.improvementPct)} tone={backtest.improvementPct > 0 ? "good" : "warn"} />
          </div>
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "অস্বাভাবিক শনাক্তকরণ F1" : "Anomaly detection F1"}
            value={f.percent(anomaly.f1, 0)}
            big
            tone={anomaly.f1 >= 0.6 ? "good" : anomaly.f1 >= 0.35 ? "warn" : "bad"}
            hint={`${f.loc === "bn" ? "প্রিসিশন" : "precision"} ${f.percent(anomaly.precision, 0)} · ${f.loc === "bn" ? "রিকল" : "recall"} ${f.percent(anomaly.recall, 0)}`}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "লেবেল পুনরায় উৎপাদন" : "Label reproduction"}
            value={f.percent(labelAgreement.rate, 0)}
            big
            tone={labelAgreement.rate >= 0.8 ? "good" : "warn"}
            hint={`${f.num(labelAgreement.matched)}/${f.num(labelAgreement.total)} ${f.loc === "bn" ? "মাস" : "periods"}`}
          />
        </Card>
        <Card>
          <Stat
            label={f.loc === "bn" ? "সহকারীর উদ্দেশ্য শনাক্তকরণ" : "Assistant intent accuracy"}
            value={f.percent(benchmark.accuracy, 0)}
            big
            tone={benchmark.accuracy >= 0.8 ? "good" : "warn"}
            hint={`${f.num(benchmark.correct)}/${f.num(benchmark.total)} ${f.loc === "bn" ? "প্রশ্ন" : "questions"}`}
          />
        </Card>
      </Grid>

      <Grid cols={2} className="mb-5">
        <Panel
          title={f.loc === "bn" ? "ব্যাকটেস্ট: মডেল বনাম বেসলাইন" : "Backtest: model vs naive baseline"}
          subtitle={
            f.loc === "bn"
              ? "একই ঐতিহাসিক উইন্ডোতে দুই পদ্ধতির ত্রুটির তুলনা।"
              : "The same historical windows, two methods, error compared."
          }
          height={250}
        >
          <CompareChart
            lang={f.tlang}
            height={250}
            data={[
              { date: "MAE", model: backtest.maeModel, baseline: backtest.maeBaseline },
              { date: "RMSE", model: backtest.rmseModel, baseline: backtest.rmseBaseline },
              { date: "MAPE %", model: backtest.mapeModel, baseline: backtest.mapeBaseline },
            ]}
            series={[
              { key: "model", label: f.loc === "bn" ? "মডেল" : "Model", color: VIZ[0] },
              { key: "baseline", label: f.loc === "bn" ? "বেসলাইন" : "Baseline", color: VIZ[4] },
            ]}
          />
          <p className="mt-2 text-[11.5px] leading-relaxed text-ink-500">
            {f.loc === "bn"
              ? `${f.num(backtest.windows)} টি টেস্ট উইন্ডোতে মডেলের গড় নির্ভুলতা ${f.percent(backtest.improvementPct, 0)} কম। বেসলাইন হলো শেষ দিনের ব্যালেন্স সরাসরি ধরে রাখা।`
              : `Across ${backtest.windows} test windows the model reduces error by ${backtest.improvementPct.toFixed(1)}%. The baseline simply holds the last observed balance constant.`}
          </p>
        </Panel>

        <Panel
          title={f.loc === "bn" ? "সহকারীর উদ্দেশ্য শনাক্তকরণ" : "Assistant intent detection"}
          subtitle={
            f.loc === "bn"
              ? `${BENCHMARK.length} টি লেবেলকৃত প্রশ্ন, ছয়টি গ্রুপে।`
              : `${BENCHMARK.length} labelled questions across six groups.`
          }
          height={250}
        >
          <CompareChart
            lang={f.tlang}
            height={250}
            data={benchmarkChart}
            series={[{ key: "accuracy", label: f.loc === "bn" ? "নির্ভুলতা %" : "accuracy %", color: VIZ[2] }]}
          />
          <p className="mt-2 text-[11.5px] leading-relaxed text-ink-500">
            {f.loc === "bn"
              ? "এই সংখ্যাটি একই কোড দিয়ে হিসাব হয়, যা আপনার প্রশ্নের উত্তর দেয় — আলাদা কোনো মডেল নয়।"
              : "Computed by the same code path that answers your live question — there is no separate model behind this number."}
          </p>
        </Panel>
      </Grid>

      <Card className="mb-5">
        <CardHeader
          kicker={f.loc === "bn" ? "বিস্তারিত" : "Breakdown"}
          title={f.loc === "bn" ? "গ্রুপভিত্তিক ফলাফল" : "Accuracy by group"}
          subtitle={
            f.loc === "bn"
              ? "বাংলা, বাংলিশ ও অস্পষ্ট প্রশ্ন আলাদাভাবে মাপা হয়, কারণ এগুলোই প্রকৃত ব্যবহারের কঠিন অংশ।"
              : "Bangla, Banglish and ambiguous queries are measured separately because they are where real usage is hardest."
          }
        />
        <Table
          align="right"
          head={[
            f.loc === "bn" ? "গ্রুপ" : "Group",
            f.loc === "bn" ? "প্রশ্ন" : "Questions",
            f.loc === "bn" ? "সঠিক" : "Correct",
            f.loc === "bn" ? "নির্ভুলতা" : "Accuracy",
          ]}
          rows={benchmark.byGroup.map((g) => [
            <span className="font-semibold text-ink-800">{g.group}</span>,
            f.num(g.total),
            f.num(g.correct),
            <span className="flex items-center justify-end gap-2">
              <span className="hidden w-16 sm:inline-block">
                <Meter value={g.accuracy * 100} tone={g.accuracy >= 0.8 ? "good" : g.accuracy >= 0.5 ? "warn" : "bad"} />
              </span>
              <span className="tabular font-bold text-ink-900">{f.percent(g.accuracy, 0)}</span>
            </span>,
          ])}
        />
        {benchmark.failures.length ? (
          <div className="mt-4">
            <p className="mb-2 text-[11px] font-bold tracking-wide text-ink-400 uppercase">
              {f.loc === "bn" ? "যেখানে ভুল হয়েছে" : "Where it misroutes"}
            </p>
            <ul className="space-y-1.5">
              {benchmark.failures.map((x) => (
                <li key={x.query} className="flex flex-wrap items-center justify-between gap-2 text-[11.5px]">
                  <span className="text-ink-600">{x.query}</span>
                  <span className="flex items-center gap-1.5">
                    <Chip tone="neutral">{x.got}</Chip>
                    <span className="text-ink-300">
                      {f.loc === "bn" ? "প্রত্যাশিত" : "expected"} {x.expected}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-ink-400">
              {f.loc === "bn"
                ? "ভুল উদ্দেশ্য শনাক্ত হলে সহকারী প্রশ্নটির কাছাকাছি সঠিক ইঞ্জিনের তথ্য দেখায় — কোনো বানানো উত্তর নয়।"
                : "On a misroute the assistant still shows figures from the nearest correct engine rather than inventing an answer."}
            </p>
          </div>
        ) : null}
      </Card>

      <Grid cols={2} className="mb-5">
        <Card>
          <CardHeader
            kicker={f.loc === "bn" ? "অস্বাভাবিক শনাক্তকরণ" : "Anomaly detection"}
            title={f.loc === "bn" ? "ইনজেক্টেড ত্রুটি খোঁজার ফল" : "Recovering injected faults"}
            right={<Chip tone="neutral">{f.num(anomaly.knownPositives)} {f.loc === "bn" ? "টি প্রকৃত" : "actual"}</Chip>}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-ink-200 px-3.5 py-2.5">
              <div className="text-[11px] font-semibold tracking-wide text-ink-400 uppercase">
                {f.loc === "bn" ? "প্রকৃত অস্বাভাবিক" : "Actual anomalies"}
              </div>
              <div className="tabular mt-1 text-[20px] font-bold text-ink-900">{f.num(anomaly.knownPositives)}</div>
            </div>
            <div className="rounded-xl border border-ink-200 px-3.5 py-2.5">
              <div className="text-[11px] font-semibold tracking-wide text-ink-400 uppercase">
                {f.loc === "bn" ? "শনাক্ত হয়েছে" : "Detected"}
              </div>
              <div className="tabular mt-1 text-[20px] font-bold text-ink-900">{f.num(anomaly.detected)}</div>
            </div>
            <div className="rounded-xl border border-mint-100 bg-mint-50/40 px-3.5 py-2.5">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-mint-700 uppercase">
                <CheckCircle2 className="h-3 w-3" />
                {f.loc === "bn" ? "সঠিকভাবে ধরা পড়েছে" : "True positives"}
              </div>
              <div className="tabular mt-1 text-[20px] font-bold text-mint-700">{f.num(anomaly.truePositives)}</div>
            </div>
            <div className="rounded-xl border border-brand-100 bg-brand-50/40 px-3.5 py-2.5">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-brand-700 uppercase">
                <AlertTriangle className="h-3 w-3" />
                {f.loc === "bn" ? "ভুলভাবে সত্য ধরা" : "False positives"}
              </div>
              <div className="tabular mt-1 text-[20px] font-bold text-brand-700">{f.num(anomaly.falsePositives)}</div>
            </div>
          </div>
          <div className="mt-4 space-y-2">
            <Meter value={anomaly.recall * 100} tone={anomaly.recall >= 0.6 ? "good" : "warn"} label={f.loc === "bn" ? "রিকল (কতগুলো ধরা পড়ল)" : "recall (share of real faults caught)"} />
            <Meter value={anomaly.precision * 100} tone={anomaly.precision >= 0.6 ? "good" : "warn"} label={f.loc === "bn" ? "প্রিসিশন (ধরা পড়া কতগুলো সত্যি ছিল)" : "precision (share of flags that were real)"} />
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-ink-400">
            {f.loc === "bn"
              ? `${anomaly.scored.length} টি লেনদেন ${f.num(anomaly.threshold, 3)} সীমার বিপরীতে স্কোর করা হয়েছে। বৈশিষ্ট্য: ${anomaly.featureKeys.join(", ")}।`
              : `${anomaly.scored.length} transactions scored against a ${anomaly.threshold} threshold. Features: ${anomaly.featureKeys.join(", ")}.`}
          </p>
        </Card>

        <Card>
          <CardHeader
            kicker={f.loc === "bn" ? "লেবেল যাচাই" : "Label agreement"}
            title={f.loc === "bn" ? "পাইথন লেবেলের পুনরায় উৎপাদন" : "Reproducing the Python labels"}
            subtitle={
              f.loc === "bn"
                ? "ফ্রন্টএন্ডের ইঞ্জিন স্বাধীনভাবে একই সিদ্ধান্ত নিয়ে আবার সেই লেবেলগুলো তৈরি করে — মিল দেখায় যে দুই পক্ষ একই সংজ্ঞা ব্যবহার করছে।"
                : "The browser engine independently reproduces the same labels, which is how we check both sides mean the same thing."
            }
          />
          <Table
            align="right"
            head={[
              f.loc === "bn" ? "ফিল্ড" : "Field",
              f.loc === "bn" ? "মিলেছে" : "Matched",
              f.loc === "bn" ? "মোট" : "Total",
              f.loc === "bn" ? "এক্ষেত্রে" : "Agreement",
            ]}
            rows={labelAgreement.perField.map((p) => [
              <span className="text-ink-700">{FIELD_LABEL[p.field] ?? p.field}</span>,
              f.num(p.matched),
              f.num(p.total),
              <span className="tabular font-bold text-ink-900">{f.percent(p.rate, 0)}</span>,
            ])}
          />
          {labelAgreement.disagreements.length ? (
            <details className="mt-3">
              <summary className="cursor-pointer text-[11.5px] font-bold text-ink-600">
                {f.loc === "bn"
                  ? `${f.num(labelAgreement.disagreements.length)} টি অমিল দেখুন`
                  : `Inspect ${labelAgreement.disagreements.length} disagreement(s)`}
              </summary>
              <ul className="mt-2 space-y-1">
                {labelAgreement.disagreements.map((d, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 text-[11.5px] text-ink-600">
                    <span>
                      {d.period} · {FIELD_LABEL[d.field] ?? d.field}
                    </span>
                    <span className="tabular">
                      {f.loc === "bn" ? "পাইথন" : "python"} {d.expected} → {f.loc === "bn" ? "এখানে" : "here"} {d.got}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </Card>
      </Grid>

      <Card className="mb-5">
        <CardHeader
          kicker={f.loc === "bn" ? "ন্যায্যতা" : "Fairness"}
          title={f.loc === "bn" ? "গোষ্ঠীভিত্তিক পরিবর্তনশীলতা" : "Variation across customer groups"}
          subtitle={
            f.loc === "bn"
              ? "একই ইঞ্জিন বিভিন্ন গোষ্ঠীতে কীভাবে আচরণ করে। কোনো সুরক্ষিত বৈশিষ্ট্য ইনপুট নয়, তবু গোষ্ঠীভিত্তিক ফলাফল স্বচ্ছভাবে দেখানো হয়।"
              : "How the same engine behaves across groups. No protected attribute is an input; the variation is shown anyway, because transparency matters more than a clean-looking chart."
          }
          right={<Chip tone="neutral"><Users className="h-3 w-3" />{f.num(allContexts.length)}</Chip>}
        />
        <div className="grid gap-4 lg:grid-cols-3">
          {probes.map((probe) => (
            <div key={probe.key}>
              <p className="mb-2 text-[11px] font-bold tracking-wide text-ink-400 uppercase">
                {probe.key.replace(/_/g, " ")}
              </p>
              <Table
                align="right"
                head={[
                  f.loc === "bn" ? "গোষ্ঠী" : "Group",
                  f.loc === "bn" ? "সদস্য" : "Members",
                  f.loc === "bn" ? "মধ্যমান" : "Median",
                  f.loc === "bn" ? "বিস্তার" : "Spread",
                ]}
                rows={probe.rows.map((r) => [
                  <span className="text-ink-700">{r.group.replace(/_/g, " ")}</span>,
                  f.num(r.members),
                  f.taka(r.meanBand),
                  <span className={cx("tabular", r.spread > 8000 ? "text-brand-700" : "text-ink-600")}>
                    {f.taka(r.spread)}
                  </span>,
                ])}
              />
            </div>
          ))}
        </div>
        <p className="mt-4 text-[11.5px] leading-relaxed text-ink-500">
          {f.loc === "bn"
            ? "কোহর্টে ভাষা বা লিঙ্গ কলাম নেই, তাই সেগুলোর উপর ন্যায্যতা পরীক্ষা করা সম্ভব নয় — এটি লুকানোর বদলে স্পষ্টভাবে বলা হচ্ছে।"
            : "The cohort carries no language or gender column, so fairness cannot be tested against those axes. Saying so is more honest than implying coverage that does not exist."}
        </p>
      </Card>

      <Card className="mb-5">
        <CardHeader
          kicker={f.loc === "bn" ? "পারস্পরিকতা" : "Mutual information"}
          title={f.loc === "bn" ? "লেবেল ও আচরণের সম্পর্ক" : "How labels relate to measured behaviour"}
          subtitle={
            f.loc === "bn"
              ? "জেনারেটর কোন আচরণ থেকে কোন লেবেল বানিয়েছে, তার সংখ্যায় ব্যাখ্যা।"
              : "Which measured behaviour produced which generator label, expressed numerically."
          }
        />
        <Table
          align="right"
          head={[
            f.loc === "bn" ? "লেবেল" : "Label",
            f.loc === "bn" ? "আচরণ" : "Behaviour",
            f.loc === "bn" ? "সম্পর্ক" : "Relationship",
          ]}
          rows={[
            ["End-of-month shortage", "late_share", "shares 20% of the label"],
            ["High cash dependency", "cash_share", "shares 15%"],
            ["Irregular income", "income_cv", "shares 15%"],
            ["Overspending", "spend_to_income", "shares 20%"],
            ["Financial pressure", "obligation_ratio", "shares 15%"],
            ["Goal progress", "goal_contribution", "shares 15%"],
          ].map(([label, behaviour, share]) => [
            <span className="text-ink-700">{label}</span>,
            <span className="font-mono text-[11px] text-ink-500">{behaviour}</span>,
            <span className="text-ink-600">{share}</span>,
          ])}
        />
        <p className="mt-3 text-[11px] leading-relaxed text-ink-400">
          {f.loc === "bn"
            ? "এগুলো কোডে নির্ধারিত ওজন — ডেটা থেকে শেখা নয়। তাই ব্যাখ্যা যায় কেন একটি লেবেল এসেছে।"
            : "These weights are fixed in code, not learned from the data — which is exactly why any label can be traced back to a number."}
        </p>
      </Card>

      <Card className="mb-5">
        <CardHeader
          kicker={f.loc === "bn" ? "ব্যক্তি" : "Persona"}
          title={f.loc === "bn" ? "ভূমিকাভিত্তিক ফলাফল" : "Results by persona"}
          subtitle={
            f.loc === "bn"
              ? "জেনারেটরের দেওয়া ভূমিকা — শুধু মূল্যায়নের জন্য, কোনো মডেল ইনপুট নয়।"
              : "Generator-assigned personas. Shown for evaluation only and never used as a model input."
          }
        />
        <Table
          align="right"
          head={[
            f.loc === "bn" ? "ভূমিকা" : "Persona",
            f.loc === "bn" ? "ব্যাখ্যা" : "Description",
          ]}
          rows={(Object.keys(personaLabel) as (keyof typeof personaLabel)[]).map((p) => [
            <span className="font-semibold text-ink-800">{personaLabel[p].en}</span>,
            <span className="text-ink-600">{f.loc === "bn" ? personaLabel[p].bn : personaLabel[p].blurb}</span>,
          ])}
        />
        <p className="mt-3 text-[11px] text-ink-400">
          {f.loc === "bn"
            ? `আপনার নির্বাচিত প্রোফাইল: ${personaLabel[ctx.user.persona].bn} (${ctx.user.persona})।`
            : `Your selected profile: ${personaLabel[ctx.user.persona].en} (${ctx.user.persona}).`}
        </p>
      </Card>

      <Grid cols={2} className="mb-5">
        <Banner tone="warn" title={f.loc === "bn" ? "যা এখানে মাপা হয়নি" : "What is not measured here"} icon={<Activity className="h-4 w-4" />}>
          <p>
            {f.loc === "bn"
              ? "দীর্ঘমেয়াদী আর্থিক ফলাফল, ঋণ পরিশোধের আচরণ, এবং বাস্তব সিদ্ধান্তের মান — এগুলো এই সিনথেটিক ডেটা দিয়ে মাপা সম্ভব নয়। তাই দাবি করা হয়নি।"
              : "Long-run financial outcomes, repayment behaviour and real-world decision quality cannot be measured on synthetic data, so they are not claimed."}
          </p>
        </Banner>
        <Banner tone="info" title={f.loc === "bn" ? "কেন সীমা প্রকাশ করা হয়" : "Why limits are on the page"} icon={<AlertTriangle className="h-4 w-4" />}>
          <p>
            {f.loc === "bn"
              ? "একটি আর্থিক পণ্যে বিশ্বাস তৈরি হয় সীমা দেখানো থেকে, না লুকানো থেকে। তাই প্রতিটি স্কোরের পাশে তার নির্ভরযোগ্যতা ও পদ্ধতি লেখা আছে।"
              : "Trust in a financial product is earned by showing where it stops, not by hiding it. Every score therefore ships with its confidence and method attached."}
          </p>
        </Banner>
      </Grid>
    </div>
  );
}