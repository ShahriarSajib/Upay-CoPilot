import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Suspense, lazy, useMemo } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useBundle } from "./hooks/useBundle";
import { Loading } from "./components/ui";
import { useCopilot } from "./data/store";
import { t as copy } from "./i18n";
import Dashboard from "./pages/Dashboard";
import Auth from "./pages/Auth";
import { useAuth } from "./data/auth";
/**
 * Only the dashboard ships in the main chunk. Every other page pulls its own
 * charts and engine code on demand, which keeps the first load small on the
 * phones most customers will use.
 */
const FinancialHealth = lazy(() => import("./pages/FinancialHealth"));
const Spending = lazy(() => import("./pages/Spending"));
const Forecast = lazy(() => import("./pages/Forecast"));
const Bills = lazy(() => import("./pages/Bills"));
const Goals = lazy(() => import("./pages/Goals"));
const Simulator = lazy(() => import("./pages/Simulator"));
const EmergencyFund = lazy(() => import("./pages/EmergencyFund"));
const CashOut = lazy(() => import("./pages/CashOut"));
const MoneySources = lazy(() => import("./pages/MoneySources"));
const Resilience = lazy(() => import("./pages/Resilience"));
const CreditReadiness = lazy(() => import("./pages/CreditReadiness"));
const Literacy = lazy(() => import("./pages/Literacy"));
const MonthlyReview = lazy(() => import("./pages/MonthlyReview"));
const Assistant = lazy(() => import("./pages/Assistant"));
const Evaluation = lazy(() => import("./pages/Evaluation"));
function Page({ children }) {
    const bundle = useBundle();
    const { status } = useCopilot();
    const memo = useMemo(() => children, [children]);
    if (status === "loading" || !bundle)
        return _jsx(Loading, {});
    return _jsx(Suspense, { fallback: _jsx(Loading, {}), children: memo });
}
export default function App() {
    const { token, loading } = useAuth();
    if (loading)
        return _jsx(Loading, {});
    if (!token)
        return _jsx(Auth, {});
    return (_jsx(Routes, { children: _jsxs(Route, { element: _jsx(Layout, {}), children: [_jsx(Route, { index: true, element: _jsx(Page, { children: _jsx(Dashboard, {}) }) }), _jsx(Route, { path: "health", element: _jsx(Page, { children: _jsx(FinancialHealth, {}) }) }), _jsx(Route, { path: "spending", element: _jsx(Page, { children: _jsx(Spending, {}) }) }), _jsx(Route, { path: "forecast", element: _jsx(Page, { children: _jsx(Forecast, {}) }) }), _jsx(Route, { path: "bills", element: _jsx(Page, { children: _jsx(Bills, {}) }) }), _jsx(Route, { path: "goals", element: _jsx(Page, { children: _jsx(Goals, {}) }) }), _jsx(Route, { path: "simulator", element: _jsx(Page, { children: _jsx(Simulator, {}) }) }), _jsx(Route, { path: "emergency-fund", element: _jsx(Page, { children: _jsx(EmergencyFund, {}) }) }), _jsx(Route, { path: "cash-out", element: _jsx(Page, { children: _jsx(CashOut, {}) }) }), _jsx(Route, { path: "money-sources", element: _jsx(Page, { children: _jsx(MoneySources, {}) }) }), _jsx(Route, { path: "resilience", element: _jsx(Page, { children: _jsx(Resilience, {}) }) }), _jsx(Route, { path: "credit-readiness", element: _jsx(Page, { children: _jsx(CreditReadiness, {}) }) }), _jsx(Route, { path: "learning", element: _jsx(Page, { children: _jsx(Literacy, {}) }) }), _jsx(Route, { path: "review", element: _jsx(Page, { children: _jsx(MonthlyReview, {}) }) }), _jsx(Route, { path: "assistant", element: _jsx(Page, { children: _jsx(Assistant, {}) }) }), _jsx(Route, { path: "evaluation", element: _jsx(Page, { children: _jsx(Evaluation, {}) }) }), _jsx(Route, { path: "*", element: _jsx(Navigate, { to: "/", replace: true }) })] }) }));
}
export function PageNotFound() {
    const { lang } = useCopilot();
    return (_jsx("div", { className: "card p-6 text-center", children: _jsx("p", { className: "text-[13px] text-ink-500", children: copy("notReady", lang) }) }));
}
