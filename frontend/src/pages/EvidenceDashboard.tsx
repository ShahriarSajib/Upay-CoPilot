import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FlaskConical,
  MinusCircle,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { apiBase } from "@/data/auth";
import { useFmt } from "@/data/store";
import { t as copy } from "@/i18n";
import { Banner, Card, CardHeader, Chip, Grid, PageHeader, Segmented, Stat, Table, bi, cx } from "@/components/ui";

/**
 * Evidence Dashboard.
 *
 * Every number on this page comes from `backend/reports/evidence_report.json`,
 * produced offline by `python -m app.evaluation.pipeline` and served by
 * `GET /api/evidence`. Nothing here is computed in the browser and nothing is
 * typed in by hand, so the page cannot disagree with the report it shows.
 *
 * The claims table is the point of the page. A metrics wall lets a reader pick
 * the flattering number; a claims table states what would have to be true
 * before the run and then records whether it held. What failed is listed
 * first, in the same size type as what passed.
 */

type Status = "supported" | "mixed" | "not_supported" | "not_measured";

interface Claim {
  id: string;
  claim: string;
  evidence_path: string;
  value: string | number | boolean | null;
  status: Status;
}

interface Headline {
  claims_supported?: number;
  claims_mixed?: number;
  claims_not_supported?: number;
  claims_total?: number;
  [key: string]: string | number | boolean | null | undefined;
}

interface RunInfo {
  generated_at?: string;
  seed?: number;
  split_path?: string;
  total_seconds?: number;
  blocks_run?: string[];
  timings_seconds?: Record<string, number>;
}

interface ForecastSummary {
  test_best_baseline?: string;
  test_best_baseline_mae?: number;
  test_best_model?: string;
  test_best_model_mae?: number;
  test_improvement_over_best_baseline_percent?: number | null;
}

interface EvidenceReport {
  run: RunInfo;
  headline: Headline;
  claims: Claim[];
  forecasting?: { summary?: Record<string, ForecastSummary> };
  anomaly?: Record<string, unknown>;
  customer_impact?: {
    detection_value?: Record<string, unknown>;
    simulation?: {
      population?: { n_customers?: number };
      placebo?: Record<string, unknown>;
    };
  };
  llm?: { headline?: Record<string, unknown> };
}

const STATUS_META: Record<Status, { label: string; tone: "good" | "warn" | "bad" | "neutral"; icon: typeof CheckCircle2 }> = {
  supported: { label: "Holds", tone: "good", icon: CheckCircle2 },
  mixed: { label: "Partly", tone: "warn", icon: MinusCircle },
  not_supported: { label: "Does not hold", tone: "bad", icon: AlertTriangle },
  not_measured: { label: "Not measured", tone: "neutral", icon: ShieldCheck },
};

const STATUS_ORDER: Status[] = ["not_supported", "mixed", "not_measured", "supported"];

function shortValue(value: unknown): string {
  if (value === null || value === undefined) return "n/a";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") {
    if (Number.isInteger(value)) return value.toLocaleString("en-US");
    return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }
  const text = String(value);
  return text.length > 96 ? `${text.slice(0, 93)}...` : text;
}

async function fetchReport(): Promise<EvidenceReport> {
  const response = await fetch(`${apiBase()}/api/evidence`);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `HTTP ${response.status}`);
  }
  return (await response.json()) as EvidenceReport;
}

export default function EvidenceDashboard() {
  const f = useFmt();
  const lang = f.loc;
  const [report, setReport] = useState<EvidenceReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Status | "all">("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReport(await fetchReport());
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchReport()
      .then((data) => {
        if (!cancelled) {
          setReport(data);
          setError(null);
        }
      })
      .catch((exc: unknown) => {
        if (!cancelled) setError(exc instanceof Error ? exc.message : String(exc));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const claims = useMemo(() => {
    const rows = report?.claims ?? [];
    return [...rows].sort(
      (a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || a.id.localeCompare(b.id),
    );
  }, [report]);

  const visible = useMemo(
    () => (filter === "all" ? claims : claims.filter((c) => c.status === filter)),
    [claims, filter],
  );

  const counts = useMemo(() => {
    const tally: Record<Status, number> = { supported: 0, mixed: 0, not_supported: 0, not_measured: 0 };
    for (const claim of claims) tally[claim.status] = (tally[claim.status] ?? 0) + 1;
    return tally;
  }, [claims]);

  const headline = useMemo(() => report?.headline ?? {}, [report]);
  const run = useMemo(() => report?.run ?? {}, [report]);

  const headlineRows = useMemo(() => {
    const rows: Array<[string, string]> = [];
    const push = (key: string, label: string) => {
      const value = headline[key];
      if (value !== undefined && value !== null) rows.push([label, shortValue(value)]);
    };
    push("spend_forecast_improvement_percent", "Spend forecast vs best naive baseline (%)");
    push("income_forecast_improvement_percent", "Income forecast vs best naive baseline (%)");
    push("anomaly_f1", "Anomaly detector F1 (test window)");
    push("anomaly_improvement_over_best_rule_percent", "Anomaly detector vs best naive rule (%)");
    push("anomaly_value_coverage", "Anomalous taka put in front of the customer");
    push("segmentation_stability_ari", "Segmentation stability across time cuts (ARI)");
    push("retrieval_recall_at_3", "Copilot retrieval recall@3");
    push("guard_legitimate_false_positive_rate", "Guard false positives on legitimate questions");
    push("live_llm_suite_status", "Live provider suite");
    push("placebo_harness_sensitive", "Simulation placebo moved nothing");
    push("customers_able_to_save", "Customers able to follow a saving plan");
    return rows;
  }, [headline]);

  const forecastRows = useMemo(() => {
    const summary = report?.forecasting?.summary;
    if (!summary) return [];
    return Object.entries(summary).map(([target, entry]) => [
      target,
      String(entry.test_best_baseline ?? "n/a"),
      Number(entry.test_best_baseline_mae ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      String(entry.test_best_model ?? "n/a"),
      Number(entry.test_best_model_mae ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      `${shortValue(entry.test_improvement_over_best_baseline_percent)}%`,
    ]);
  }, [report]);

  const detection = report?.customer_impact?.detection_value ?? {};
  const simulation = report?.customer_impact?.simulation ?? {};
  const placebo = simulation.placebo ?? {};
  const llmHeadline = report?.llm?.headline ?? {};

  if (loading && !report) {
    return (
      <div>
        <PageHeader title={copy("evidence", lang)} subtitle={bi(lang, "Loading the evaluation report…", "মূল্যায়ন রিপোর্ট লোড হচ্ছে…")} />
        <Card>
          <p className="text-[13px] text-ink-500">{bi(lang, "Reading backend/reports/evidence_report.json", "backend/reports/evidence_report.json পড়া হচ্ছে")}</p>
        </Card>
      </div>
    );
  }

  if (error && !report) {
    return (
      <div>
        <PageHeader title={copy("evidence", lang)} />
        <Banner tone="warn" title={bi(lang, "No report on disk", "ডিস্কে কোনো রিপোর্ট নেই")}>
          <p className="text-[13px] leading-relaxed">{error}</p>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-ink-900 px-3 py-2 text-[11.5px] text-white">PYTHONPATH=backend python -m app.evaluation.pipeline</pre>
          <button
            type="button"
            onClick={() => void load()}
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-ink-300 px-3 py-1.5 text-[12px] font-bold text-ink-700 transition hover:border-brand-400 hover:text-brand-700"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {bi(lang, "Try again", "আবার চেষ্টা করুন")}
          </button>
        </Banner>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={copy("evidence", lang)}
        subtitle={bi(
          lang,
          "What the product claims, what the measurements showed, and what did not hold. Generated offline from the untouched test window; nothing on this page is typed in by hand.",
          "পণ্য যা দাবি করে, পরিমাপ যা দেখিয়েছে, এবং যা প্রমাণিত হয়নি। অন্টাচেড টেস্ট উইন্ডো থেকে অফলাইনে তৈরি; এই পাতার কোনো সংখ্যা হাতে লেখা নয়।",
        )}
        actions={
          <>
            <Chip tone="brand">
              <FlaskConical className="h-3 w-3" />
              {counts.supported}/{claims.length} {bi(lang, "hold", "প্রমাণিত")}
            </Chip>
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-ink-300 px-3 py-1.5 text-[12px] font-bold text-ink-700 transition hover:border-brand-400 hover:text-brand-700"
            >
              <RefreshCw className={cx("h-3.5 w-3.5", loading && "animate-spin")} />
              {bi(lang, "Reload", "রিলোড")}
            </button>
          </>
        }
      />

      <div className="mb-5">
        <Banner tone="neutral" title={bi(lang, "How to read this", "কীভাবে পড়বেন")}>
          <p className="text-[13px] leading-relaxed">
            {bi(
              lang,
              "Each claim below states, before the run, what would have to be true. The thresholds live in backend/app/evaluation/pipeline.py::CLAIM_RULES. Rows are sorted so what did not hold appears first — a metrics wall would let you pick the flattering number.",
              "নিচের প্রতিটি দাবি চালানোর আগেই বলে দেয় কী সত্য হতে হবে। থ্রেশহোল্ড backend/app/evaluation/pipeline.py::CLAIM_RULES-এ আছে। যা প্রমাণিত হয়নি তা আগে দেখানো হয়।",
            )}
          </p>
        </Banner>
      </div>

      <Grid cols={4} className="mb-5">
        <Stat label={bi(lang, "Claims holding", "প্রমাণিত দাবি")} value={`${counts.supported}`} hint={`${claims.length} ${bi(lang, "total", "মোট")}`} big />
        <Stat
          label={bi(lang, "Partly holding", "আংশিক")}
          value={`${counts.mixed}`}
          hint={bi(lang, "threshold missed", "থ্রেশহোল্ড মিলেনি")}
          tone="warn"
        />
        <Stat
          label={bi(lang, "Not holding", "প্রমাণিত হয়নি")}
          value={`${counts.not_supported}`}
          hint={bi(lang, "reported, not hidden", "লুকানো হয়নি")}
          tone={counts.not_supported > 0 ? "bad" : "good"}
        />
        <Stat
          label={bi(lang, "Last run", "সর্বশেষ রান")}
          value={run.total_seconds ? `${run.total_seconds}s` : "n/a"}
          hint={run.generated_at ? new Date(run.generated_at).toLocaleString("en-US") : ""}
        />
      </Grid>

      <Card className="mb-5">
        <CardHeader
          kicker={bi(lang, "Headline", "শিরোনাম")}
          title={bi(lang, "The numbers a judge should see first", "যে সংখ্যাগুলো আগে দেখা উচিত")}
          right={
            <Chip tone="neutral">
              seed {run.seed ?? "n/a"} · {bi(lang, "blocks", "ব্লক")} {run.blocks_run?.length ?? 0}
            </Chip>
          }
        />
        <Table
          head={[bi(lang, "Measure", "পরিমাপ"), bi(lang, "Value", "মান")]}
          rows={headlineRows.map(([label, value]) => [label, <span className="tabular font-semibold text-ink-900">{value}</span>])}
        />
        {run.split_path ? (
          <p className="mt-3 text-[11.5px] text-ink-500">
            {bi(lang, "Splits at", "স্প্লিট")} <span className="font-mono">{run.split_path}</span>
          </p>
        ) : null}
      </Card>

      <Card className="mb-5">
        <CardHeader
          kicker={bi(lang, "Claims", "দাবি")}
          title={bi(lang, "Stated in advance, scored after", "আগে থেকে বলা, পরে মাপা")}
          right={
            <Segmented
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: `${bi(lang, "All", "সব")} ${claims.length}` },
                { value: "not_supported", label: `${bi(lang, "Not holding", "হয়নি")} ${counts.not_supported}` },
                { value: "mixed", label: `${bi(lang, "Partly", "আংশিক")} ${counts.mixed}` },
                { value: "supported", label: `${bi(lang, "Holding", "হয়েছে")} ${counts.supported}` },
              ]}
            />
          }
        />
        <div className="divide-y divide-ink-100">
          {visible.map((claim) => {
            const meta = STATUS_META[claim.status] ?? STATUS_META.not_measured;
            const Icon = meta.icon;
            const open = expanded === claim.id;
            return (
              <div key={claim.id} className="py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-start gap-3">
                  <Chip tone={meta.tone}>
                    <Icon className="h-3 w-3" />
                    {meta.label}
                  </Chip>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13.5px] leading-snug font-semibold text-ink-900">{claim.claim}</p>
                    <p className="mt-1 tabular text-[13px] text-ink-700">{shortValue(claim.value)}</p>
                    <button
                      type="button"
                      onClick={() => setExpanded(open ? null : claim.id)}
                      className="mt-1 text-[11.5px] font-bold text-brand-700 hover:underline"
                    >
                      {open ? bi(lang, "Hide evidence", "প্রমাণ লুকান") : bi(lang, "Show evidence", "প্রমাণ দেখুন")}
                    </button>
                    {open ? (
                      <p className="mt-1 break-all rounded-lg bg-ink-50 px-2.5 py-1.5 font-mono text-[11px] text-ink-600">
                        {claim.evidence_path}
                      </p>
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })}
          {visible.length === 0 ? (
            <p className="py-4 text-[13px] text-ink-500">{bi(lang, "No claims with this status.", "এই অবস্থার কোনো দাবি নেই।")}</p>
          ) : null}
        </div>
      </Card>

      {forecastRows.length ? (
        <Card className="mb-5">
          <CardHeader
            kicker={bi(lang, "Forecasting", "পূর্বাভাস")}
            title={bi(lang, "Shipped model against the best naive baseline", "শিপ করা মডেল বনাম সেরা নাইভ বেসলাইন")}
            subtitle={bi(
              lang,
              "MAE on the untouched test window. A model that cannot beat a three-month moving average does not earn its complexity.",
              "অন্টাচেড টেস্ট উইন্ডোতে MAE। তিন মাসের মুভিং এভারেজকে হারাতে না পারলে জটিলতা অর্থহীন।",
            )}
          />
          <Table
            head={[bi(lang, "Target", "টার্গেট"), bi(lang, "Best baseline", "সেরা বেসলাইন"), `${bi(lang, "Baseline", "বেসলাইন")} MAE`, bi(lang, "Shipped model", "শিপ মডেল"), `${bi(lang, "Model", "মডেল")} MAE`, bi(lang, "Improvement", "উন্নতি")]}
            rows={forecastRows}
            align="right"
          />
        </Card>
      ) : null}

      <Grid cols={2} className="mb-5">
        <Card>
          <CardHeader
            kicker={bi(lang, "Anomaly detection", "অস্বাভাবিক শনাক্তকরণ")}
            title={bi(lang, "Caught, and what it cost in trust", "যা ধরা পড়েছে, আর বিশ্বাসের খরচ")}
          />
          <div className="space-y-2 text-[13px]">
            <Row label={bi(lang, "Anomalous taka in window", "উইন্ডোতে অস্বাভাবিক টাকা")} value={shortValue(detection.total_anomalous_value)} />
            <Row label={bi(lang, "Flagged", "ফ্ল্যাগ করা")} value={shortValue(detection.caught_anomalous_value)} />
            <Row label={bi(lang, "Coverage", "কভারেজ")} value={shortValue(detection.value_coverage)} tone="good" />
            <Row label={bi(lang, "Wrongly flagged share", "ভুল ফ্ল্যাগের অংশ")} value={shortValue(detection.wrongly_flagged_share_of_flagged_value)} tone="bad" />
            <Row label={bi(lang, "Detector vs best naive rule", "ডিটেক্টর বনাম নাইভ রুল")} value={`${shortValue(headline.anomaly_improvement_over_best_rule_percent)}%`} tone="good" />
          </div>
        </Card>

        <Card>
          <CardHeader
            kicker={bi(lang, "Customer impact", "গ্রাহক প্রভাব")}
            title={bi(lang, "Simulation with a placebo control", "প্লেসিবো নিয়ন্ত্রণসহ সিমুলেশন")}
            subtitle={bi(
              lang,
              "The same engine runs the baseline, two stated policies, and a zero intervention. The placebo must move nothing.",
              "একই ইঞ্জিন বেসলাইন, দুটি নীতি এবং শূন্য হস্তক্ষেপ চালায়। প্লেসিবো কিছু নাড়াতে পারে না।",
            )}
          />
          <div className="space-y-2 text-[13px]">
            <Row label={bi(lang, "Placebo moved nothing", "প্লেসিবো নড়েনি")} value={shortValue(placebo.harness_sensitive)} tone={placebo.harness_sensitive ? "good" : "bad"} />
            <Row label={bi(lang, "Customers simulated", "অনুকরণ করা গ্রাহক")} value={shortValue(simulation.population?.n_customers ?? null)} />
            <Row label={bi(lang, "Able to follow a saving plan", "সঞ্চয় পরিকল্পনা মানতে পারে")} value={shortValue(headline.customers_able_to_save)} tone="warn" />
            <Row label={bi(lang, "Deficit warning: novel share", "ঘাটতি সতর্কতা: নতুন তথ্যের অংশ")} value={shortValue(headline.deficit_warning_novel_share)} tone="bad" />
          </div>
        </Card>
      </Grid>

      <Card className="mb-5">
        <CardHeader
          kicker={bi(lang, "Copilot safety", "কোপাইলট নিরাপত্তা")}
          title={bi(lang, "Guards, grounding and tools", "গার্ড, গ্রাউন্ডিং ও টুল")}
        />
        <Table
          head={[bi(lang, "Check", "পরীক্ষা"), bi(lang, "Result", "ফলাফল")]}
          rows={Object.entries(llmHeadline).map(([key, value]) => [
            <span className="font-semibold text-ink-700">{key}</span>,
            <span className={cx("tabular", value === true || value === 1 || value === 1.0 ? "text-mint-700" : value === false ? "text-brand-700" : "text-ink-900")}>
              {shortValue(value)}
            </span>,
          ])}
        />
      </Card>

      <Card>
        <CardHeader
          kicker={bi(lang, "Reproduce", "পুনরায় চালান")}
          title={bi(lang, "The report is a build artefact", "রিপোর্ট একটি বিল্ড আর্টিফ্যাক্ট")}
        />
        <pre className="overflow-x-auto rounded-lg bg-ink-900 px-3 py-2.5 text-[11.5px] leading-relaxed text-white">{`PYTHONPATH=backend python -m app.evaluation.pipeline     # fit, score, write JSON + markdown
PYTHONPATH=backend python backend/scripts/run_evaluation.py --markdown-only   # re-render only
curl ${apiBase()}/api/evidence/summary                       # what this page reads`}</pre>
        <p className="mt-3 text-[12px] leading-relaxed text-ink-500">
          {bi(
            lang,
            "Splits are disjoint by construction (train 2026-01..05, validation 06..07, test 08..09), seed 42 everywhere, and test is scored once by the block that needs it. Ground-truth tables — personas, injected patterns, behaviour flags — are used for scoring only.",
            "স্প্লিট গঠনগতভাবে বিচ্ছিন্ন (ট্রেইন ২০২৬-০১..০৫, ভ্যালিডেশন ০৬..০৭, টেস্ট ০৮..০৯), সব জায়গায় সিড ৪২, এবং টেস্ট একবারই স্কোর করা হয়। গ্রাউন্ড ট্রুথ টেবিল শুধু স্কোরিংয়ে ব্যবহৃত হয়।",
          )}
        </p>
      </Card>
    </div>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" | "warn" }) {
  const color = tone === "good" ? "text-mint-700" : tone === "bad" ? "text-brand-700" : tone === "warn" ? "text-amber-ink" : "text-ink-900";
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-ink-500">{label}</span>
      <span className={cx("tabular font-semibold", color)}>{value}</span>
    </div>
  );
}
