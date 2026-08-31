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
export type Meal = components["schemas"]["MealResponse"];
export type MealUpdate = components["schemas"]["MealUpdate"];
export type DietStats = components["schemas"]["DietStatsResponse"];
export type ExpenseAnalysis = components["schemas"]["ExpenseAnalysisResponse"];
export type MonthBudget = components["schemas"]["MonthBudget"];
export type MonthBudgetUpdate = components["schemas"]["MonthBudgetUpdate"];
export type CrossPeriod = components["schemas"]["CrossPeriodResponse"];
export type ExpectedRecord = components["schemas"]["ExpectedRecord"];
export type ExpectedWrite = components["schemas"]["ExpectedWrite"];
export type ConfirmExpected = components["schemas"]["ConfirmExpected"];
export type PrepaidRecord = components["schemas"]["PrepaidRecord"];
export type PrepaidWrite = components["schemas"]["PrepaidWrite"];
export type PrepaidUpdate = components["schemas"]["PrepaidUpdate"];
export type HomeSummary = components["schemas"]["HomeSummary"];

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
  if (response.status === 204) return undefined as T;
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
  pendingTransactions: () =>
    request<Transaction[]>("/api/pending-transactions"),
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
  meals: () => request<Meal[]>("/api/meals"),
  updateMeal: (id: number, entry: MealUpdate) =>
    request<Meal>(`/api/meals/${id}`, {
      method: "PATCH",
      body: JSON.stringify(entry),
    }),
  deleteMeal: (id: number) =>
    request<void>(`/api/meals/${id}`, { method: "DELETE" }),
  dietStats: (startDate: string, endDate: string) => {
    const query = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
    });
    return request<DietStats>(`/api/meals/stats?${query}`);
  },
  expenseAnalysis: (
    granularity: "month" | "year",
    period: string | null,
    basis: "cash" | "amortized",
  ) => {
    const query = new URLSearchParams({ granularity, basis });
    if (period) query.set("period", period);
    return request<ExpenseAnalysis>(`/api/analysis/expenses?${query}`);
  },
  updateMonthBudget: (month: string, budget: MonthBudgetUpdate) =>
    request<MonthBudget>(`/api/analysis/budgets/${month}`, {
      method: "PUT",
      body: JSON.stringify(budget),
    }),
  crossPeriod: () => request<CrossPeriod>("/api/cross-period"),
  createExpected: (entry: ExpectedWrite, idempotencyKey: string) =>
    request("/api/cross-period/expected", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(entry),
    }),
  updateExpected: (record: ExpectedRecord, entry: ExpectedWrite) =>
    request<void>(`/api/cross-period/expected/${record.source}/${record.id}`, {
      method: "PATCH",
      body: JSON.stringify(entry),
    }),
  confirmExpected: (
    record: ExpectedRecord,
    entry: ConfirmExpected,
    idempotencyKey: string,
  ) => request(`/api/cross-period/expected/${record.source}/${record.id}/confirm`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(entry),
  }),
  deleteExpected: (record: ExpectedRecord) =>
    request<void>(`/api/cross-period/expected/${record.source}/${record.id}`, {
      method: "DELETE",
    }),
  createPrepaid: (entry: PrepaidWrite, idempotencyKey: string) =>
    request("/api/cross-period/prepaid", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(entry),
    }),
  updatePrepaid: (id: number, entry: PrepaidUpdate) =>
    request<void>(`/api/cross-period/prepaid/${id}`, {
      method: "PATCH",
      body: JSON.stringify(entry),
    }),
  deletePrepaid: (id: number) =>
    request<void>(`/api/cross-period/prepaid/${id}`, { method: "DELETE" }),
  homeSummary: () => request<HomeSummary>("/api/home"),
};
