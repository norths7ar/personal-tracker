export function unique(values: Array<string | null | undefined>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))].sort();
}

export function commonValue<T>(values: T[]): T | undefined {
  if (!values.length) return undefined;
  return values.every((value) => Object.is(value, values[0])) ? values[0] : undefined;
}

export function formatMoney(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
  }).format(value);
}

export function formatDate(value: Date): string {
  return new Intl.DateTimeFormat("en-CA").format(value);
}

export function csvCell(value: unknown): string {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

export const selectClass = "form-select";
export const transactionTypes = ["支出", "收入", "迁移"] as const;
