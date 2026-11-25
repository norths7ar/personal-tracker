import "@/styles/app.css";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { api, ApiError } from "@/api/client";
import { AppShell } from "@/components/app-shell";
import { LoginPage } from "@/features/auth/login-page";

const LedgerPage = lazy(() =>
  import("@/features/ledger/ledger-page").then((module) => ({
    default: module.LedgerPage,
  })),
);
const NotesPage = lazy(() =>
  import("@/features/notes/notes-page").then((module) => ({
    default: module.NotesPage,
  })),
);
const TodoPage = lazy(() =>
  import("@/features/todo/todo-page").then((module) => ({ default: module.TodoPage })),
);
const RecordPage = lazy(() =>
  import("@/features/record/record-page").then((module) => ({
    default: module.RecordPage,
  })),
);
const PendingPage = lazy(() =>
  import("@/features/pending/pending-page").then((module) => ({
    default: module.PendingPage,
  })),
);
const DietPage = lazy(() =>
  import("@/features/diet/diet-page").then((module) => ({ default: module.DietPage })),
);
const JobsPage = lazy(() =>
  import("@/features/jobs/jobs-page").then((module) => ({ default: module.JobsPage })),
);
const AnalysisPage = lazy(() =>
  import("@/features/analysis/analysis-page").then((module) => ({
    default: module.AnalysisPage,
  })),
);
const SettingsPage = lazy(() =>
  import("@/features/settings/settings-page").then((module) => ({ default: module.SettingsPage })),
);

export function App() {
  const queryClient = useQueryClient();
  const currentUser = useQuery({
    queryKey: ["auth", "me"],
    queryFn: api.currentUser,
    retry: false,
  });

  if (currentUser.isPending) {
    return <div className="app-loading">正在载入…</div>;
  }
  if (currentUser.error instanceof ApiError && currentUser.error.status === 401) {
    return (
      <LoginPage onSuccess={() => queryClient.invalidateQueries({ queryKey: ["auth", "me"] })} />
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
          <Route path="/notes" element={<NotesPage />} />
          <Route path="/ledger" element={<LedgerPage />} />
          <Route path="/diet" element={<DietPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/record" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
