import type { ReactNode } from "react";
import type { Lang } from "@/types";
import { useCopilot } from "@/data/store";

/* ------------------------------------------------------------------ *
 * Primitives. Every screen is assembled from these so that spacing,
 * type scale and evidence affordances stay identical across pages.
 * ------------------------------------------------------------------ */

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function Card({
  children,
  className,
  as: As = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  return <As className={cx("card p-5", className)}>{children}</As>;
}

export function CardHeader({
  title,
  subtitle,
  right,
  kicker,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  kicker?: ReactNode;
}) {
  return (
    <header className="mb-4 flex items-start justify-between gap-4">
      <div className="min-w-0">
        {kicker ? <div className="mb-1 text-[11px] font-semibold tracking-wider text-brand-600 uppercase">{kicker}</div> : null}
        <h2 className="text-[15px] leading-tight font-semibold text-ink-900">{title}</h2>
        {subtitle ? <p className="mt-1 text-[13px] leading-relaxed text-ink-500">{subtitle}</p> : null}
      </div>
      {right ? <div className="shrink-0">{right}</div> : null}
    </header>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="animate-in mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[26px] leading-tight font-bold tracking-[-0.02em] text-ink-900">{title}</h1>
        {subtitle ? <p className="mt-1.5 max-w-2xl text-[14px] leading-relaxed text-ink-500">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

type Tone = "neutral" | "brand" | "good" | "warn" | "bad";

const TONE_CHIP: Record<Tone, string> = {
  neutral: "bg-ink-100 text-ink-700 border-ink-200",
  brand: "bg-brand-50 text-brand-700 border-brand-200",
  good: "bg-mint-50 text-mint-700 border-mint-100",
  warn: "bg-amber-50 text-amber-ink border-amber-100",
  bad: "bg-brand-50 text-brand-700 border-brand-200",
};

export function Chip({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold",
        TONE_CHIP[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
  big,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  big?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="truncate text-[11px] font-semibold tracking-wide text-ink-400 uppercase">{label}</div>
      <div
        className={cx(
          "tabular mt-1 font-bold tracking-[-0.02em]",
          big ? "text-[28px]" : "text-[20px]",
          tone === "good" ? "text-mint-700" : tone === "warn" ? "text-amber-ink" : tone === "bad" ? "text-brand-700" : "text-ink-900",
        )}
      >
        {value}
      </div>
      {hint ? <div className="mt-0.5 text-[12px] leading-snug text-ink-500">{hint}</div> : null}
    </div>
  );
}

export function Meter({
  value,
  max = 100,
  tone = "brand",
  label,
}: {
  value: number;
  max?: number;
  tone?: "brand" | "good" | "warn" | "bad" | "muted";
  label?: ReactNode;
}) {
  const pct = Math.max(0, Math.min(100, (value / (max || 1)) * 100));
  const fill: Record<string, string> = {
    brand: "bg-brand-500",
    good: "bg-mint-500",
    warn: "bg-amber-500",
    bad: "bg-brand-600",
    muted: "bg-ink-300",
  };
  return (
    <div>
      {label ? <div className="mb-1.5 text-[12px] text-ink-600">{label}</div> : null}
      <div className="h-2 w-full overflow-hidden rounded-full bg-ink-100">
        <div className={cx("h-full rounded-full transition-all duration-500", fill[tone])} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function Grid({ cols = 2, children, className }: { cols?: number; children: ReactNode; className?: string }) {
  const map: Record<number, string> = {
    1: "sm:grid-cols-1",
    2: "sm:grid-cols-2",
    3: "sm:grid-cols-2 lg:grid-cols-3",
    4: "sm:grid-cols-2 lg:grid-cols-4",
  };
  return <div className={cx("grid gap-4", map[cols], className)}>{children}</div>;
}

export function Banner({
  tone = "neutral",
  title,
  children,
  icon,
}: {
  tone?: "neutral" | "info" | "warn" | "danger" | "good";
  title?: ReactNode;
  children?: ReactNode;
  icon?: ReactNode;
}) {
  const tones: Record<string, string> = {
    neutral: "border-ink-200 bg-ink-50 text-ink-700",
    info: "border-viz-5/20 bg-sky-50 text-sky-900",
    warn: "border-amber-200 bg-amber-50 text-amber-ink",
    danger: "border-brand-200 bg-brand-50 text-brand-800",
    good: "border-mint-100 bg-mint-50 text-mint-700",
  };
  return (
    <div className={cx("rounded-xl border px-4 py-3 text-[13px] leading-relaxed", tones[tone])}>
      <div className="flex items-start gap-2.5">
        {icon ? <span className="mt-0.5 shrink-0">{icon}</span> : null}
        <div className="min-w-0">
          {title ? <div className="font-semibold">{title}</div> : null}
          {children}
        </div>
      </div>
    </div>
  );
}

export function Table({ head, rows, align = "left" }: { head: string[]; rows: (ReactNode)[][]; align?: "left" | "right" }) {
  return (
    <div className="scroll-thin -mx-5 overflow-x-auto px-5">
      <table className="w-full min-w-[440px] border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-ink-200">
            {head.map((h) => (
              <th
                key={h}
                className={cx(
                  "pb-2 text-[11px] font-semibold tracking-wide text-ink-400 uppercase",
                  align === "right" ? "text-right" : "text-left",
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-ink-100 last:border-0">
              {row.map((cell, j) => (
                <td key={j} className={cx("py-2.5 align-middle", align === "right" ? "text-right" : "text-left")}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-ink-200 bg-white p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={cx(
            "rounded-md px-3 py-1.5 text-[12px] font-semibold transition",
            value === o.value ? "bg-ink-900 text-white" : "text-ink-500 hover:text-ink-800",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  display,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  display: string;
}) {
  return (
    <label className="block">
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <span className="text-[12px] font-semibold text-ink-700">{label}</span>
        <span className="tabular text-[13px] font-bold text-ink-900">{display}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-ink-200 accent-brand-600"
      />
    </label>
  );
}

export function Loading() {
  const { lang } = useCopilot();
  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center gap-4 text-center">
      <div className="h-9 w-9 animate-spin rounded-full border-[3px] border-ink-200 border-t-brand-500" />
      <p className={cx("text-[13px] text-ink-500", lang === "bn" && "bn")}>{lang === "bn" ? "হিসাব হচ্ছে…" : "Computing…"}</p>
    </div>
  );
}

/** Bilingual label helper: shows the Bangla string when the UI is Bangla. */
export function bi(lang: Lang, en: string, bn: string): string {
  return lang === "bn" ? bn : en;
}