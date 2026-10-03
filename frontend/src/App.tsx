import { Suspense, lazy, useMemo, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useBundle } from "./hooks/useBundle";
import { Loading } from "./components/ui";
import { useCopilot } from "./data/store";
import { t as copy } from "./i18n";

import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Signup from "./pages/Signup";

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

function Page({ children }: { children: ReactNode }) {
  const bundle = useBundle();
  const { status, isAuthenticated } = useCopilot();
  const memo = useMemo(() => children, [children]);
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (status === "loading" || !bundle) return <Loading />;
  return <Suspense fallback={<Loading />}>{memo}</Suspense>;
}

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, status } = useCopilot();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  const { isAuthenticated } = useCopilot();

  return (
    <Routes>
      <Route path="login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
      <Route path="signup" element={isAuthenticated ? <Navigate to="/" replace /> : <Signup />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route
          index
          element={
            <Page>
              <Dashboard />
            </Page>
          }
        />
        <Route
          path="health"
          element={
            <Page>
              <FinancialHealth />
            </Page>
          }
        />
        <Route
          path="spending"
          element={
            <Page>
              <Spending />
            </Page>
          }
        />
        <Route
          path="forecast"
          element={
            <Page>
              <Forecast />
            </Page>
          }
        />
        <Route
          path="bills"
          element={
            <Page>
              <Bills />
            </Page>
          }
        />
        <Route
          path="goals"
          element={
            <Page>
              <Goals />
            </Page>
          }
        />
        <Route
          path="simulator"
          element={
            <Page>
              <Simulator />
            </Page>
          }
        />
        <Route
          path="emergency-fund"
          element={
            <Page>
              <EmergencyFund />
            </Page>
          }
        />
        <Route
          path="cash-out"
          element={
            <Page>
              <CashOut />
            </Page>
          }
        />
        <Route
          path="money-sources"
          element={
            <Page>
              <MoneySources />
            </Page>
          }
        />
        <Route
          path="resilience"
          element={
            <Page>
              <Resilience />
            </Page>
          }
        />
        <Route
          path="credit-readiness"
          element={
            <Page>
              <CreditReadiness />
            </Page>
          }
        />
        <Route
          path="learning"
          element={
            <Page>
              <Literacy />
            </Page>
          }
        />
        <Route
          path="review"
          element={
            <Page>
              <MonthlyReview />
            </Page>
          }
        />
        <Route
          path="assistant"
          element={
            <Page>
              <Assistant />
            </Page>
          }
        />
        <Route
          path="evaluation"
          element={
            <Page>
              <Evaluation />
            </Page>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function PageNotFound() {
  const { lang } = useCopilot();
  return (
    <div className="card p-6 text-center">
      <p className="text-[13px] text-ink-500">{copy("notReady", lang)}</p>
    </div>
  );
}