import { useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import { AppShell } from "@/components/app-shell";
import { LoginPage } from "@/pages/login-page";

const LedgerPage = lazy(() =>
  import("@/pages/ledger-page").then((module) => ({ default: module.LedgerPage })),
);
const RecordPage = lazy(() =>
  import("@/pages/record-page").then((module) => ({ default: module.RecordPage })),
);
const PendingPage = lazy(() =>
  import("@/pages/pending-page").then((module) => ({ default: module.PendingPage })),
);
const DietPage = lazy(() =>
  import("@/pages/diet-page").then((module) => ({ default: module.DietPage })),
);
const AnalysisPage = lazy(() =>
  import("@/pages/analysis-page").then((module) => ({ default: module.AnalysisPage })),
);

export function App() {
  const queryClient = useQueryClient();
  const currentUser = useQuery({ queryKey: ["current-user"], queryFn: api.currentUser, retry: false });

  if (currentUser.isPending) {
    return <div className="grid min-h-screen place-items-center text-sm text-neutral-500">正在载入…</div>;
  }
  if (currentUser.error instanceof ApiError && currentUser.error.status === 401) {
    return <LoginPage onSuccess={() => queryClient.invalidateQueries({ queryKey: ["current-user"] })} />;
  }
  if (currentUser.isError) {
    return <div className="grid min-h-screen place-items-center text-sm text-red-600">{currentUser.error.message}</div>;
  }

  const logout = async () => {
    await api.logout();
    queryClient.clear();
    window.location.assign("/");
  };

  return (
    <AppShell onLogout={logout}>
      <Suspense fallback={<p className="text-sm text-neutral-500">正在载入页面…</p>}>
        <Routes>
          <Route path="/record" element={<RecordPage />} />
          <Route path="/pending" element={<PendingPage />} />
          <Route path="/ledger" element={<LedgerPage />} />
          <Route path="/diet" element={<DietPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="*" element={<Navigate to="/record" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
