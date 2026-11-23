import { type ExpectedRecord, type PrepaidRecord } from "@/api/client";

export type ExpectedAction =
  { mode: "create" } | { mode: "edit" | "confirm"; record: ExpectedRecord };

export type PrepaidAction = { mode: "create" } | { mode: "edit"; record: PrepaidRecord };

export function categoryLabel(record: { category?: string | null; subcategory?: string | null }) {
  return [record.category, record.subcategory].filter(Boolean).join(" / ") || "—";
}

export function categoryValues(
  categories: Record<string, string[]>,
  category: string,
  subcategory: string,
  preserveCurrent = false,
): [string | null, string | null] {
  if (preserveCurrent) return [category || null, subcategory || null];
  const selectedCategory = category || Object.keys(categories)[0] || null;
  if (!selectedCategory) return [null, null];
  const children = categories[selectedCategory] ?? [];
  return [
    selectedCategory,
    subcategory && children.includes(subcategory) ? subcategory : (children[0] ?? null),
  ];
}

export function money(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
  }).format(value);
}
