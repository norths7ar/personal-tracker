import "@/styles/app.css";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import { AppShell } from "@/components/app-shell";
import { LoginPage } from "@/pages/login-page";

const LedgerPage = lazy(() =>
  import("@/pages/ledger-page").then((module) => ({
    default: module.LedgerPage,
  })),
);
const TodoPage = lazy(() =>
  import("@/pages/todo-page").then((module) => ({ default: module.TodoPage })),
);
const RecordPage = lazy(() =>
  import("@/pages/record-page").then((module) => ({
    default: module.RecordPage,
  })),
);
const PendingPage = lazy(() =>
  import("@/pages/pending-page").then((module) => ({
    default: module.PendingPage,
  })),
);
const DietPage = lazy(() =>
  import("@/pages/diet-page").then((module) => ({ default: module.DietPage })),
);
const AnalysisPage = lazy(() =>
  import("@/pages/analysis-page").then((module) => ({
    default: module.AnalysisPage,
  })),
);
const CrossPeriodPage = lazy(() =>
  import("@/pages/cross-period-page").then((module) => ({
    default: module.CrossPeriodPage,
  })),
);
const SettingsPage = lazy(() =>
  import("@/pages/settings-page").then((module) => ({ default: module.SettingsPage })),
);

export function App() {
  const queryClient = useQueryClient();
  const currentUser = useQuery({
    queryKey: ["current-user"],
    queryFn: api.currentUser,
    retry: false,
  });

  if (currentUser.isPending) {
    return <div className="app-loading">正在载入…</div>;
  }
  if (currentUser.error instanceof ApiError && currentUser.error.status === 401) {
    return (
      <LoginPage onSuccess={() => queryClient.invalidateQueries({ queryKey: ["current-user"] })} />
    );
  }
  if (currentUser.isError) {
    return <div className="app-error">{currentUser.error.message}</div>;
  }

  const logout = async () => {
    await api.logout();
    queryClient.clear();
    window.location.assign("/");
  };

  return (
    <AppShell onLogout={logout}>
      <Suspense fallback={<p className="muted-text">正在载入页面…</p>}>
        <Routes>
          <Route path="/record" element={<RecordPage />} />
          <Route path="/todo" element={<TodoPage />} />
          <Route path="/pending" element={<PendingPage />} />
          <Route path="/ledger" element={<LedgerPage />} />
          <Route path="/diet" element={<DietPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/cross-period" element={<CrossPeriodPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/record" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
