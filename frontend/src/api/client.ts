import type { components } from "./schema";

export type Transaction = components["schemas"]["TransactionResponse"];
export type TransactionUpdate = components["schemas"]["TransactionUpdate"];
export type TransactionPreparation = components["schemas"]["TransactionPreparationResponse"];
export type TransactionCreate = components["schemas"]["TransactionCreateRequest"];
export type MealPreparation = components["schemas"]["MealPreparationResponse"];
export type MealCreate = components["schemas"]["MealCreateRequest"];
export type BatchRecord = components["schemas"]["BatchRecord"];
export type CaptureItem = components["schemas"]["CaptureItem"];
export type CapturePending = components["schemas"]["PendingCaptureResponse"];
export type CaptureSuggestion = components["schemas"]["CaptureSuggestion"];
export type Meal = components["schemas"]["MealResponse"];
export type MealUpdate = components["schemas"]["MealUpdate"];
export type MealBulkChanges = Partial<Pick<MealUpdate, "date" | "time" | "meal_type" | "notes">>;
export type DietStats = components["schemas"]["DietStatsResponse"];
export type ExpenseAnalysis = components["schemas"]["ExpenseAnalysisResponse"];
export type MonthBudget = components["schemas"]["MonthBudget"];
export type MonthBudgetUpdate = components["schemas"]["MonthBudgetUpdate"];
export type Plans = components["schemas"]["PlansResponse"];
export type ExpectedRecord = components["schemas"]["ExpectedRecord"];
export type ExpectedWrite = components["schemas"]["ExpectedWrite"];
export type ConfirmExpected = components["schemas"]["ConfirmExpected"];
export type HomeSummary = components["schemas"]["HomeSummary"];
export type RefundCreate = components["schemas"]["RefundCreate"];
export type SubscriptionCreate = components["schemas"]["SubscriptionCreate"];
export type Todo = components["schemas"]["TodoResponse"];
export type TodoWrite = components["schemas"]["TodoWrite"];
export type TodoState = components["schemas"]["TodoState"];
export type TodoMove = components["schemas"]["TodoMove"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const { headers, ...options } = init ?? {};
  const response = await fetch(path, {
    credentials: "include",
    ...options,
    headers: { "Content-Type": "application/json", ...headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string | Array<{ msg?: string }>;
    } | null;
    throw new ApiError(
      response.status,
      typeof body?.detail === "string"
        ? body.detail
        : Array.isArray(body?.detail)
          ? body.detail.map((item) => item.msg ?? "输入无效").join("；")
          : `请求失败 (${response.status})`,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  submitCapture: (text: string, defaultDate: string, key: string) =>
    request<{ id: number; duplicate: boolean }>("/api/capture/submissions", {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ text, default_date: defaultDate }),
    }),
  capturePending: () => request<CapturePending>("/api/capture/pending"),
  confirmCapture: (id: number, record: BatchRecord) =>
    request<{ id: number; duplicate: boolean }>(`/api/capture/items/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify(record),
    }),
  retryCapture: (id: number) =>
    request<{ id: number }>(`/api/capture/items/${id}/retry`, { method: "POST" }),
  discardCapture: (id: number) =>
    request<void>(`/api/capture/items/${id}/discard`, { method: "POST" }),
  captureSuggestions: () => request<CaptureSuggestion[]>("/api/capture/suggestions"),
  pinPhrase: (text: string) =>
    request<CaptureSuggestion[]>("/api/capture/phrases", {
      method: "PUT",
      body: JSON.stringify({ text }),
    }),
  unpinPhrase: (text: string) =>
    request<CaptureSuggestion[]>("/api/capture/phrases", {
      method: "DELETE",
      body: JSON.stringify({ text }),
    }),
  todos: () => request<Todo[]>("/api/todos"),
  createTodo: (entry: TodoWrite) =>
    request<Todo>("/api/todos", {
      method: "POST",
      body: JSON.stringify(entry),
    }),
  updateTodo: (id: number, entry: TodoWrite) =>
    request<Todo>(`/api/todos/${id}`, {
      method: "PUT",
      body: JSON.stringify(entry),
    }),
  setTodoState: (id: number, state: TodoState) =>
    request<Todo>(`/api/todos/${id}/state`, {
      method: "POST",
      body: JSON.stringify(state),
    }),
  moveTodo: (id: number, move: TodoMove) =>
    request<void>(`/api/todos/${id}/move`, {
      method: "POST",
      body: JSON.stringify(move),
    }),
  deleteTodo: (id: number) => request<void>(`/api/todos/${id}`, { method: "DELETE" }),
  currentUser: () => request<{ authenticated: boolean }>("/api/auth/me"),
  login: (password: string) =>
    request<{ authenticated: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  logout: () => request<{ authenticated: boolean }>("/api/auth/logout", { method: "POST" }),
  transactions: () => request<Transaction[]>("/api/ledger/transactions"),
  pendingTransactions: () => request<Transaction[]>("/api/ledger/pending"),
  updateTransaction: (id: number, changes: TransactionUpdate) =>
    request<Transaction>(`/api/ledger/transactions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
  createRefund: (id: number, entry: RefundCreate, idempotencyKey: string) =>
    request<{ id: number; duplicate: boolean }>(`/api/ledger/transactions/${id}/refunds`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(entry),
    }),
  createSubscription: (id: number, entry: SubscriptionCreate, idempotencyKey: string) =>
    request<{ id: number; duplicate: boolean }>(`/api/ledger/transactions/${id}/subscription`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(entry),
    }),
  deleteTransactions: (ids: number[]) =>
    request<{ deleted_count: number }>("/api/ledger/transactions/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  updateTransactions: (
    ids: number[],
    changes: Partial<Pick<TransactionUpdate, "category" | "subcategory" | "notes">>,
  ) =>
    request<{ updated_count: number }>("/api/ledger/transactions/bulk-update", {
      method: "PATCH",
      body: JSON.stringify({ ids, ...changes }),
    }),
  prepareTransaction: (type: TransactionCreate["type"], description: string) =>
    request<TransactionPreparation>("/api/capture/transactions/prepare", {
      method: "POST",
      body: JSON.stringify({ type, description }),
    }),
  createTransaction: (entry: TransactionCreate, idempotencyKey: string) =>
    request<{ id: number; duplicate: boolean }>("/api/capture/transactions", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(entry),
    }),
  prepareMeal: (description: string, time: string | null) =>
    request<MealPreparation>("/api/capture/meals/prepare", {
      method: "POST",
      body: JSON.stringify({ description, time }),
    }),
  createMeal: (entry: MealCreate, idempotencyKey: string) =>
    request<{ id: number; duplicate: boolean }>("/api/capture/meals", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(entry),
    }),
  meals: () => request<Meal[]>("/api/diet/meals"),
  updateMeal: (id: number, entry: MealUpdate) =>
    request<Meal>(`/api/diet/meals/${id}`, {
      method: "PATCH",
      body: JSON.stringify(entry),
    }),
  updateMeals: (ids: number[], changes: MealBulkChanges) =>
    request<{ updated_count: number }>("/api/diet/meals/bulk-update", {
      method: "PATCH",
      body: JSON.stringify({ ids, ...changes }),
    }),
  deleteMeals: (ids: number[]) =>
    request<{ deleted_count: number }>("/api/diet/meals/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  deleteMeal: (id: number) => request<void>(`/api/diet/meals/${id}`, { method: "DELETE" }),
  dietStats: (startDate: string, endDate: string) => {
    const query = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
    });
    return request<DietStats>(`/api/diet/stats?${query}`);
  },
  expenseAnalysis: (
    granularity: "month" | "year",
    period: string | null,
    basis: "cash" | "amortized",
  ) => {
    const query = new URLSearchParams({ granularity, basis });
    if (period) query.set("period", period);
    return request<ExpenseAnalysis>(`/api/ledger/analysis?${query}`);
  },
  updateMonthBudget: (month: string, budget: MonthBudgetUpdate) =>
    request<MonthBudget>(`/api/ledger/budgets/${month}`, {
      method: "PUT",
      body: JSON.stringify(budget),
    }),
  plans: () => request<Plans>("/api/ledger/plans"),
  createExpected: (entry: ExpectedWrite, idempotencyKey: string) =>
    request("/api/ledger/plans", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(entry),
    }),
  updateExpected: (record: ExpectedRecord, entry: ExpectedWrite) =>
    request<void>(`/api/ledger/plans/${record.source}/${record.id}`, {
      method: "PATCH",
      body: JSON.stringify(entry),
    }),
  confirmExpected: (record: ExpectedRecord, entry: ConfirmExpected, idempotencyKey: string) =>
    request(`/api/ledger/plans/${record.source}/${record.id}/confirm`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(entry),
    }),
  deleteExpected: (record: ExpectedRecord) =>
    request<void>(`/api/ledger/plans/${record.source}/${record.id}`, {
      method: "DELETE",
    }),
  homeSummary: () => request<HomeSummary>("/api/capture/home"),
};

export type Settings = components["schemas"]["SettingsResponse"];
export type ModelSettingsUpdate = components["schemas"]["ModelSettingsUpdate"];
export type RecordSettingsUpdate = components["schemas"]["RecordSettingsUpdate"];
export type AccessSettingsUpdate = components["schemas"]["AccessSettingsUpdate"];
export type PromptSettingsUpdate = components["schemas"]["PromptSettingsUpdate"];

export const settingsApi = {
  get: () => request<Settings>("/api/settings"),
  prompts: (body: PromptSettingsUpdate) =>
    request<Settings>("/api/settings/prompts", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  model: (body: ModelSettingsUpdate) =>
    request<Settings>("/api/settings/model", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  records: (body: RecordSettingsUpdate) =>
    request<Settings>("/api/settings/records", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  access: (body: AccessSettingsUpdate) =>
    request<Settings>("/api/settings/access", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};
