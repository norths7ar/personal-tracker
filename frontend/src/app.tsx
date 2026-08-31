import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";

import { ApiError, api } from "@/api/client";
import { AppShell } from "@/components/app-shell";
import { LoginPage } from "@/pages/login-page";
import { LedgerPage } from "@/pages/ledger-page";

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
      <Routes>
        <Route path="/ledger" element={<LedgerPage />} />
        <Route path="*" element={<Navigate to="/ledger" replace />} />
      </Routes>
    </AppShell>
  );
}
