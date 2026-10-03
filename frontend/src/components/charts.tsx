import type { ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { shortDate, takaCompact, monthLabel } from "@/lib/format";
import type { Lang } from "@/types";
import { cx } from "./ui";

/**
 * Recharts wrappers.
 *
 * All of them share one axis/grid/tooltip treatment so charts read as a single
 * system, and every value formatter respects the customer's language and
 * numeral preference rather than hard-coding "en-US".
 */

const AXIS = { stroke: "#cbc7c1", tickLine: false, axisLine: false, fontSize: 11 } as const;
const GRID = { stroke: "#e3e1dd", strokeDasharray: "3 3", vertical: false } as const;

export const VIZ = ["#d71f42", "#0f766e", "#7c3aed", "#b45309", "#0369a1", "#be185d", "#4d7c0f", "#0891b2"];

function axisMoney(lang: Lang) {
  return (v: number) => takaCompact(v, lang);
}

/** Recharts hands tooltips loosely-typed values; narrow them here once. */
function moneyTooltip(lang: Lang) {
  return (v: unknown, n: unknown): [string, string] => [takaCompact(Number(v ?? 0), lang), String(n)];
}

export function Panel({
  title,
  subtitle,
  right,
  children,
  className,
  height = 240,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  height?: number;
}) {
  return (
    <section className={cx("card p-5", className)}>
      <header className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-ink-900">{title}</h3>
          {subtitle ? <p className="mt-1 text-[12px] leading-relaxed text-ink-500">{subtitle}</p> : null}
        </div>
        {right ? <div className="shrink-0">{right}</div> : null}
      </header>
      <div style={{ height }}>{children}</div>
    </section>
  );
}

/** Loose chart row: any numeric or label column, keyed by name. */
export type ChartPoint = Record<string, string | number | undefined>;

/** Daily balance / income-expense area chart. */
export function AreaTrend({
  data,
  keys,
  xKey = "date",
  lang = "en",
  formatter = axisMoney(lang),
  height = 240,
}: {
  data: ChartPoint[];
  keys: { key: string; label: string; color?: string }[];
  xKey?: string;
  lang?: Lang;
  formatter?: (v: number) => string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
        <defs>
          {keys.map((k, i) => (
            <linearGradient key={k.key} id={`grad-${k.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={k.color ?? VIZ[i]} stopOpacity={0.28} />
              <stop offset="100%" stopColor={k.color ?? VIZ[i]} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid {...GRID} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={(v: string) => shortDate(v, lang)} minTickGap={28} />
        <YAxis {...AXIS} tickFormatter={formatter} width={52} />
        <Tooltip
          contentStyle={{ fontSize: 12 }}
          formatter={
            (v: unknown, n: unknown) => [formatter(Number(v ?? 0)), String(n)] as [string, string]
          }
          labelFormatter={(v) => shortDate(String(v), lang)}
        />
        <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }} iconType="circle" iconSize={7} />
        {keys.map((k, i) => (
          <Area
            key={k.key}
            type="monotone"
            dataKey={k.key}
            name={k.label}
            stroke={k.color ?? VIZ[i]}
            strokeWidth={2}
            fill={`url(#grad-${k.key})`}
            dot={false}
            activeDot={{ r: 3 }}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function MoneyBars({
  data,
  xKey = "date",
  keys,
  lang = "en",
  stacked = false,
  height = 240,
  xTick,
}: {
  data: ChartPoint[];
  xKey?: string;
  keys: { key: string; label: string; color?: string }[];
  lang?: Lang;
  stacked?: boolean;
  height?: number;
  xTick?: (v: string) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: 4, bottom: 0 }} barGap={2}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={xTick ?? ((v: string) => shortDate(v, lang))} minTickGap={20} />
        <YAxis {...AXIS} tickFormatter={axisMoney(lang)} width={52} />
        <Tooltip
          contentStyle={{ fontSize: 12 }}
          cursor={{ fill: "#f1f0ee", radius: 6 }}
          formatter={moneyTooltip(lang)}
          labelFormatter={(v) => shortDate(String(v), lang)}
        />
        <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }} iconType="circle" iconSize={7} />
        {keys.map((k, i) => (
          <Bar
            key={k.key}
            dataKey={k.key}
            name={k.label}
            fill={k.color ?? VIZ[i]}
            stackId={stacked ? "stack" : undefined}
            radius={stacked ? 0 : [4, 4, 0, 0]}
            maxBarSize={26}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Monthly income vs spending bars with a surplus line. */
export function MonthlyFlowChart({
  data,
  lang = "en",
  height = 240,
}: {
  data: { key: string; income: number; spend: number; savings: number }[];
  lang?: Lang;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="key" {...AXIS} tickFormatter={(v: string) => monthLabel(v, lang)} />
        <YAxis {...AXIS} tickFormatter={axisMoney(lang)} width={52} />
        <Tooltip
          contentStyle={{ fontSize: 12 }}
          cursor={{ fill: "#f1f0ee", radius: 6 }}
          formatter={moneyTooltip(lang)}
          labelFormatter={(v) => monthLabel(String(v), lang)}
        />
        <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }} iconType="circle" iconSize={7} />
        <Bar dataKey="income" name={lang === "bn" ? "আয়" : "Income"} fill={VIZ[1]} radius={[4, 4, 0, 0]} maxBarSize={22} />
        <Bar dataKey="spend" name={lang === "bn" ? "ব্যয়" : "Spending"} fill={VIZ[0]} radius={[4, 4, 0, 0]} maxBarSize={22} />
        <Line type="monotone" dataKey="savings" name={lang === "bn" ? "সঞ্চয়" : "Savings"} stroke={VIZ[3]} strokeWidth={2} dot={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Donut({
  data,
  lang = "en",
  height = 220,
  valueKey = "value",
  nameKey = "name",
  centerLabel,
  centerValue,
}: {
  data: { name: string; value: number }[];
  lang?: Lang;
  height?: number;
  valueKey?: string;
  nameKey?: string;
  centerLabel?: string;
  centerValue?: string;
}) {
  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={data} dataKey={valueKey} nameKey={nameKey} innerRadius="58%" outerRadius="86%" paddingAngle={2} strokeWidth={0}>
            {data.map((_, i) => (
              <Cell key={i} fill={VIZ[i % VIZ.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ fontSize: 12 }}
            formatter={moneyTooltip(lang)}
          />
        </PieChart>
      </ResponsiveContainer>
      {centerValue ? (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="tabular text-[18px] font-bold text-ink-900">{centerValue}</span>
          {centerLabel ? <span className="text-[11px] text-ink-500">{centerLabel}</span> : null}
        </div>
      ) : null}
    </div>
  );
}

/** Baseline vs scenario line comparison — the simulator's core visual. */
export function CompareChart({
  data,
  series,
  lang = "en",
  height = 260,
  reference,
  referenceLabel,
}: {
  data: Array<Record<string, string | number>>;
  series: { key: string; label: string; color?: string }[];
  lang?: Lang;
  height?: number;
  reference?: number;
  referenceLabel?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 8, left: 4, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="date" {...AXIS} tickFormatter={(v: string) => monthLabel(v, lang)} />
        <YAxis {...AXIS} tickFormatter={axisMoney(lang)} width={52} />
        <Tooltip
          contentStyle={{ fontSize: 12 }}
          formatter={moneyTooltip(lang)}
          labelFormatter={(v) => monthLabel(String(v), lang)}
        />
        <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }} iconType="circle" iconSize={7} />
        {reference !== undefined ? (
          <ReferenceLine y={reference} stroke="#7b746c" strokeDasharray="4 4" label={{ value: referenceLabel, fontSize: 10, fill: "#7b746c" }} />
        ) : null}
        {series.map((s, i) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color ?? VIZ[i]}
            strokeWidth={2.2}
            dot={false}
            strokeDasharray={s.key === "scenario" ? undefined : "5 4"}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Forecast with an uncertainty band drawn as a translucent range. */
export function ForecastChart({
  points,
  lang = "en",
  height = 280,
  buffer,
}: {
  points: { date: string; balance: number; lower: number; upper: number; belowBuffer: boolean }[];
  lang?: Lang;
  height?: number;
  buffer?: number;
}) {
  const data = points.map((p) => ({ ...p, band: Math.max(0, p.upper - p.lower), floor: p.lower }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
        <defs>
          <linearGradient id="band" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#d71f42" stopOpacity={0.16} />
            <stop offset="100%" stopColor="#d71f42" stopOpacity={0.04} />
          </linearGradient>
        </defs>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="date" {...AXIS} tickFormatter={(v: string) => shortDate(v, lang)} minTickGap={26} />
        <YAxis {...AXIS} tickFormatter={axisMoney(lang)} width={52} />
        <Tooltip
          contentStyle={{ fontSize: 12 }}
          formatter={moneyTooltip(lang)}
          labelFormatter={(v) => shortDate(String(v), lang)}
        />
        <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }} iconType="circle" iconSize={7} />
        {buffer !== undefined ? (
          <ReferenceLine
            y={Math.max(0, buffer)}
            stroke="#b45309"
            strokeDasharray="4 4"
            label={{ value: lang === "bn" ? "রিজার্ভ" : "buffer", fontSize: 10, fill: "#b45309" }}
          />
        ) : null}
        <Area dataKey="band" name={lang === "bn" ? "আস্থা ব্যাপ্তি" : "uncertainty"} stackId="b" stroke="none" fill="url(#band)" />
        <Area
          type="monotone"
          dataKey="floor"
          name={lang === "bn" ? "নিম্ন সীমা" : "lower"}
          stackId="b"
          stroke="none"
          fill="transparent"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="balance"
          name={lang === "bn" ? "প্রকৃতিপত ব্যালেন্স" : "projected balance"}
          stroke="#d71f42"
          strokeWidth={2.4}
          fill="none"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function Legend2({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5 text-[11px] text-ink-600">
          <span className="h-2 w-2 rounded-full" style={{ background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}