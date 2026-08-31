import type { components } from "./schema";

export type Transaction = components["schemas"]["TransactionResponse"];
export type TransactionUpdate = components["schemas"]["TransactionUpdate"];
export type CategoryConfiguration = Record<string, Record<string, string[]>>;
export type TransactionPreparation = components["schemas"]["TransactionPreparationResponse"];
export type TransactionCreate = components["schemas"]["TransactionCreateRequest"];
export type MealPreparation = components["schemas"]["MealPreparationResponse"];
export type MealCreate = components["schemas"]["MealCreateRequest"];
export type BatchRecord = components["schemas"]["BatchRecord"];
export type BatchPreparation = components["schemas"]["BatchPrepareResponse"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { headers, ...options } = init ?? {};
  const response = await fetch(path, {
    credentials: "include",
    ...options,
    headers: { "Content-Type": "application/json", ...headers },
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
  prepareTransaction: (type: TransactionCreate["type"], description: string) =>
    request<TransactionPreparation>("/api/entries/transactions/prepare", {
      method: "POST",
      body: JSON.stringify({ type, description }),
    }),
  createTransaction: (entry: TransactionCreate, idempotencyKey: string) =>
    request<{ id: number; duplicate: boolean }>("/api/entries/transactions", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(entry),
    }),
  prepareMeal: (description: string, time: string) =>
    request<MealPreparation>("/api/entries/meals/prepare", {
      method: "POST",
      body: JSON.stringify({ description, time }),
    }),
  createMeal: (entry: MealCreate, idempotencyKey: string) =>
    request<{ id: number; duplicate: boolean }>("/api/entries/meals", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(entry),
    }),
  prepareBatch: (text: string, defaultDate: string) =>
    request<BatchPreparation>("/api/entries/batch/prepare", {
      method: "POST",
      body: JSON.stringify({ text, default_date: defaultDate }),
    }),
  saveBatch: (submissionId: string, records: BatchRecord[]) =>
    request<{ saved_count: number; duplicate: boolean }>("/api/entries/batch", {
      method: "POST",
      body: JSON.stringify({ submission_id: submissionId, records }),
    }),
};
