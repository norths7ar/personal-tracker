import type { components } from "./schema";

export type Transaction = components["schemas"]["TransactionResponse"];
export type TransactionUpdate = components["schemas"]["TransactionUpdate"];
export type CategoryConfiguration = Record<string, Record<string, string[]>>;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(response.status, body?.detail ?? `请求失败 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  currentUser: () => request<{ authenticated: boolean }>("/api/auth/me"),
  login: (password: string) =>
    request<{ authenticated: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  logout: () =>
    request<{ authenticated: boolean }>("/api/auth/logout", { method: "POST" }),
  transactions: () => request<Transaction[]>("/api/transactions"),
  categories: () => request<CategoryConfiguration>("/api/config/categories"),
  updateTransaction: (id: number, changes: TransactionUpdate) =>
    request<Transaction>(`/api/transactions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  deleteTransactions: (ids: number[]) =>
    request<{ deleted_count: number }>("/api/transactions/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
};
