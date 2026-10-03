import type { ReactNode } from "react";
import { useState } from "react";
import { ChevronDown, Database, FlaskConical, ShieldCheck } from "lucide-react";
import type { Evidence, Lang } from "@/types";
import { taka, percent } from "@/lib/format";
import { Chip, cx } from "./ui";
import { useCopilot } from "@/data/store";

/* ------------------------------------------------------------------ *
 * Evidence is a first-class UI object, not a footnote.
 *
 * Every number in this product is produced by an engine that returns an
 * Evidence record: the metrics it used, the reasons it weighted them, the
 * assumptions it made and the source tables it read. The components below
 * render that record so a customer can always get from "what should I do?"
 * down to "which rows produced that?".
 * ------------------------------------------------------------------ */

function formatValue(value: number | string, unit?: Evidence["metrics"][number]["unit"], lang: Lang = "en") {
  if (typeof value === "string") return value;
  switch (unit) {
    case "bdt":
      return taka(value, { lang });
    case "percent":
      return percent(value, lang, 1);
    case "ratio":
      return value.toFixed(2);
    default:
      return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
  }
}

export function ConfidenceDot({ value }: { value: number }) {
  const tone = value >= 0.7 ? "bg-mint-500" : value >= 0.5 ? "bg-amber-500" : "bg-brand-500";
  const label = value >= 0.7 ? "high" : value >= 0.5 ? "moderate" : "low";
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-ink-500">
      <span className={cx("h-1.5 w-1.5 rounded-full", tone)} />
      {label} · {(value * 100).toFixed(0)}%
    </span>
  );
}

export function EvidenceButton({ evidence, className }: { evidence: Evidence; className?: string }) {
  const [open, setOpen] = useState(false);
  const { pushEvidence, lang } = useCopilot();
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          if (!open) pushEvidence(evidence);
        }}
        className={cx(
          "inline-flex items-center gap-1.5 rounded-full border border-ink-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-ink-600 transition hover:border-brand-300 hover:text-brand-700",
          className,
        )}
      >
        <FlaskConical className="h-3.5 w-3.5" />
        {lang === "bn" ? "প্রমাণ" : "evidence"}
        <ChevronDown className={cx("h-3 w-3 transition-transform", open && "rotate-180")} />
      </button>
      {open ? (
        <div className="mt-3">
          <EvidenceBody evidence={evidence} />
        </div>
      ) : null}
    </>
  );
}

export function EvidenceBody({ evidence }: { evidence: Evidence }) {
  const { lang } = useCopilot();
  const bn = lang === "bn";
  return (
    <div className="animate-in rounded-xl border border-ink-200 bg-ink-50/70 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-[12px] font-bold text-ink-900">{evidence.headline}</div>
        <ConfidenceDot value={evidence.confidence} />
      </div>
      <p className="mb-3 text-[12px] leading-relaxed text-ink-600">{evidence.confidenceNote}</p>

      {evidence.metrics.length ? (
        <>
          <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-ink-400 uppercase">
            {bn ? "মূল সংখ্যা" : "Key numbers"}
          </div>
          <div className="mb-4 grid gap-2 sm:grid-cols-2">
            {evidence.metrics.map((m) => (
              <div key={m.id} className="rounded-lg border border-ink-200 bg-white px-3 py-2">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-[11px] font-semibold text-ink-500">{m.label}</span>
                  <span className="tabular shrink-0 text-[13px] font-bold text-ink-900">
                    {formatValue(m.value, m.unit, lang)}
                  </span>
                </div>
                {m.detail ? <div className="mt-0.5 text-[11px] leading-snug text-ink-400">{m.detail}</div> : null}
              </div>
            ))}
          </div>
        </>
      ) : null}

      {evidence.reasons.length ? (
        <>
          <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-ink-400 uppercase">{bn ? "কেন" : "Why"}</div>
          <ul className="mb-4 space-y-1.5">
            {evidence.reasons.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px] leading-relaxed text-ink-700">
                <span
                  className={cx(
                    "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                    r.polarity === "positive" ? "bg-mint-500" : r.polarity === "negative" ? "bg-brand-500" : "bg-ink-300",
                  )}
                />
                {r.text}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        {evidence.assumptions.length ? (
          <div>
            <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-ink-400 uppercase">
              {bn ? "ধরণাবিধান" : "Assumptions"}
            </div>
            <ul className="space-y-1 text-[12px] leading-relaxed text-ink-600">
              {evidence.assumptions.map((a, i) => (
                <li key={i}>· {a}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {evidence.sources.length ? (
          <div>
            <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-ink-400 uppercase">
              {bn ? "উৎস" : "Sources"}
            </div>
            <ul className="space-y-1 text-[12px] leading-relaxed text-ink-600">
              {evidence.sources.map((s, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <Database className="mt-0.5 h-3 w-3 shrink-0 text-ink-400" />
                  <span className="font-mono text-[11px]">{s}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      {evidence.evaluation?.length ? (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-ink-200 pt-3">
          {evidence.evaluation.map((e) => (
            <Chip key={e.metric} tone="neutral">
              {e.metric}: {e.value.toFixed(3)} {e.unit}
            </Chip>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/** Inline, always-visible disclaimer used on the readiness and evaluation screens. */
export function ResponsibleNotice({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-start gap-2.5 rounded-xl border border-ink-200 bg-white px-4 py-3 text-[12px] leading-relaxed text-ink-600">
      <span className="mt-0.5 shrink-0 text-mint-600">{icon ?? <ShieldCheck className="h-4 w-4" />}</span>
      <div>{children}</div>
    </div>
  );
}

export function GroundTruthStrip({ children }: { children: ReactNode }) {
  return <div className="gt-stripes rounded-xl border border-amber-200/70 px-4 py-3">{children}</div>;
}