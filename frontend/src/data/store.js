import { jsx as _jsx } from "react/jsx-runtime";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, } from "react";
import { fullDate as fmtFullDate, monthLabel as fmtMonth, num as fmtNum, pctPoints as fmtPctPoints, percent as fmtPercent, shortDate as fmtShortDate, taka as fmtTaka, takaCompact as fmtCompact, weekdayLabel as fmtWeekday, } from "@/lib/format";
import { loadDataset } from "./snapshot";
import { buildUserContext } from "./context";
const CopilotContext = createContext(null);
const STORAGE_USER = "upay.copilot.user";
const STORAGE_LANG = "upay.copilot.lang";
const STORAGE_NUMERALS = "upay.copilot.numerals";
export function CopilotProvider({ children }) {
    const [status, setStatus] = useState("loading");
    const [error, setError] = useState(null);
    const [data, setData] = useState(null);
    const [userId, setUserIdState] = useState(() => localStorage.getItem(STORAGE_USER) ?? "");
    const [lang, setLangState] = useState(() => localStorage.getItem(STORAGE_LANG) || "en");
    const [banglaNumerals, setBanglaNumeralsState] = useState(() => localStorage.getItem(STORAGE_NUMERALS) === "1");
    const [evidenceStack, setEvidenceStack] = useState([]);
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
            .catch((err) => {
            if (controller.signal.aborted)
                return;
            setError(err instanceof Error ? err.message : String(err));
            setStatus("error");
        });
        return () => controller.abort();
    }, []);
    const setUserId = useCallback((id) => {
        setUserIdState(id);
        localStorage.setItem(STORAGE_USER, id);
    }, []);
    const setLang = useCallback((next) => {
        setLangState(next);
        localStorage.setItem(STORAGE_LANG, next);
    }, []);
    const setBanglaNumerals = useCallback((on) => {
        setBanglaNumeralsState(on);
        localStorage.setItem(STORAGE_NUMERALS, on ? "1" : "0");
    }, []);
    const pushEvidence = useCallback((evidence) => {
        setEvidenceStack((stack) => [evidence, ...stack].slice(0, 12));
    }, []);
    const popEvidence = useCallback(() => setEvidenceStack((stack) => stack.slice(1)), []);
    const clearEvidence = useCallback(() => setEvidenceStack([]), []);
    const ctx = useMemo(() => (data && userId ? buildUserContext(data, userId) : null), [data, userId]);
    const value = useMemo(() => ({
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
    }), [
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
    ]);
    return _jsx(CopilotContext.Provider, { value: value, children: children });
}
export function useCopilot() {
    const value = useContext(CopilotContext);
    if (!value)
        throw new Error("useCopilot must be used inside <CopilotProvider>");
    return value;
}
/** Convenience hook: the built context for the selected customer. */
export function useUserContext() {
    const { ctx } = useCopilot();
    if (!ctx)
        throw new Error("Dataset is not loaded yet");
    return ctx;
}
/** Locale-aware formatter bound to the current language + numeral preference. */
export function useFmt() {
    const { lang, banglaNumerals } = useCopilot();
    return useMemo(() => {
        const loc = banglaNumerals ? "bn" : lang;
        return {
            loc,
            lang,
            /** Text in the UI language (so copy and numbers agree). */
            tlang: loc,
            taka: (n, o) => fmtTaka(n, { lang: loc, decimals: o?.decimals }),
            compact: (n) => fmtCompact(n, loc),
            num: (n, decimals = 0) => fmtNum(n, loc, decimals),
            percent: (n, decimals = 1) => fmtPercent(n, loc, decimals),
            pct: (n, decimals = 0) => fmtPctPoints(n, loc, decimals),
            shortDate: (v) => fmtShortDate(v, loc),
            fullDate: (v) => fmtFullDate(v, loc),
            month: (key) => fmtMonth(key, loc),
            weekday: (v) => fmtWeekday(v, loc),
            /** Pick the right side of a bilingual pair. */
            bi: (en, bn) => (lang === "bn" ? bn : en),
        };
    }, [lang, banglaNumerals]);
}
