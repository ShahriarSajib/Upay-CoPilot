import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Evidence, Lang, User } from "@/types";
import {
  fullDate as fmtFullDate,
  monthLabel as fmtMonth,
  num as fmtNum,
  pctPoints as fmtPctPoints,
  percent as fmtPercent,
  shortDate as fmtShortDate,
  taka as fmtTaka,
  takaCompact as fmtCompact,
  weekdayLabel as fmtWeekday,
} from "@/lib/format";
import { loadDataset, type Dataset } from "./snapshot";
import { buildUserContext, type UserContext } from "./context";

interface CopilotState {
  status: "loading" | "ready" | "error";
  error: string | null;
  data: Dataset | null;
  users: User[];
  userId: string;
  setUserId: (id: string) => void;
  ctx: UserContext | null;
  lang: Lang;
  setLang: (lang: Lang) => void;
  /** Display numbers in Bangla numerals even when the copy is English. */
  banglaNumerals: boolean;
  setBanglaNumerals: (on: boolean) => void;
  evidenceStack: Evidence[];
  pushEvidence: (evidence: Evidence) => void;
  popEvidence: () => void;
  clearEvidence: () => void;
}

const CopilotContext = createContext<CopilotState | null>(null);

const STORAGE_USER = "upay.copilot.user";
const STORAGE_LANG = "upay.copilot.lang";
const STORAGE_NUMERALS = "upay.copilot.numerals";

export function CopilotProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<CopilotState["status"]>("loading");
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<Dataset | null>(null);
  const [userId, setUserIdState] = useState<string>(
    () => localStorage.getItem(STORAGE_USER) ?? "",
  );
  const [lang, setLangState] = useState<Lang>(
    () => (localStorage.getItem(STORAGE_LANG) as Lang) || "en",
  );
  const [banglaNumerals, setBanglaNumeralsState] = useState<boolean>(
    () => localStorage.getItem(STORAGE_NUMERALS) === "1",
  );
  const [evidenceStack, setEvidenceStack] = useState<Evidence[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    loadDataset(controller.signal)
      .then((dataset) => {
        setData(dataset);
        setUserIdState((current) => {
          const valid = dataset.cohort.includes(current);
          return valid && current ? current : dataset.cohort[0];
        });
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
        setStatus("error");
      });
    return () => controller.abort();
  }, []);

  const setUserId = useCallback((id: string) => {
    setUserIdState(id);
    localStorage.setItem(STORAGE_USER, id);
  }, []);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    localStorage.setItem(STORAGE_LANG, next);
  }, []);

  const setBanglaNumerals = useCallback((on: boolean) => {
    setBanglaNumeralsState(on);
    localStorage.setItem(STORAGE_NUMERALS, on ? "1" : "0");
  }, []);

  const pushEvidence = useCallback((evidence: Evidence) => {
    setEvidenceStack((stack) => [evidence, ...stack].slice(0, 12));
  }, []);
  const popEvidence = useCallback(() => setEvidenceStack((stack) => stack.slice(1)), []);
  const clearEvidence = useCallback(() => setEvidenceStack([]), []);

  const ctx = useMemo(() => (data && userId ? buildUserContext(data, userId) : null), [data, userId]);

  const value = useMemo<CopilotState>(
    () => ({
      status,
      error,
      data,
      users: data?.users ?? [],
      userId,
      setUserId,
      ctx,
      lang,
      setLang,
      banglaNumerals,
      setBanglaNumerals,
      evidenceStack,
      pushEvidence,
      popEvidence,
      clearEvidence,
    }),
    [
      status,
      error,
      data,
      userId,
      setUserId,
      ctx,
      lang,
      setLang,
      banglaNumerals,
      setBanglaNumerals,
      evidenceStack,
      pushEvidence,
      popEvidence,
      clearEvidence,
    ],
  );

  return <CopilotContext.Provider value={value}>{children}</CopilotContext.Provider>;
}

export function useCopilot(): CopilotState {
  const value = useContext(CopilotContext);
  if (!value) throw new Error("useCopilot must be used inside <CopilotProvider>");
  return value;
}

/** Convenience hook: the built context for the selected customer. */
export function useUserContext(): UserContext {
  const { ctx } = useCopilot();
  if (!ctx) throw new Error("Dataset is not loaded yet");
  return ctx;
}

/** Locale-aware formatter bound to the current language + numeral preference. */
export function useFmt() {
  const { lang, banglaNumerals } = useCopilot();
  return useMemo(() => {
    const loc: Lang = banglaNumerals ? "bn" : lang;
    return {
      loc,
      lang,
      /** Text in the UI language (so copy and numbers agree). */
      tlang: loc,
      taka: (n: number, o?: { decimals?: boolean }) => fmtTaka(n, { lang: loc, decimals: o?.decimals }),
      compact: (n: number) => fmtCompact(n, loc),
      num: (n: number, decimals = 0) => fmtNum(n, loc, decimals),
      percent: (n: number, decimals = 1) => fmtPercent(n, loc, decimals),
      pct: (n: number, decimals = 0) => fmtPctPoints(n, loc, decimals),
      shortDate: (v: string | Date) => fmtShortDate(v, loc),
      fullDate: (v: string | Date) => fmtFullDate(v, loc),
      month: (key: string) => fmtMonth(key, loc),
      weekday: (v: string | Date) => fmtWeekday(v, loc),
      /** Pick the right side of a bilingual pair. */
      bi: (en: string, bn: string) => (lang === "bn" ? bn : en),
    };
  }, [lang, banglaNumerals]);
}