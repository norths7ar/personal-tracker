import { type ExpectedRecord } from "@/api/client";

export type ExpectedAction =
  { mode: "create" } | { mode: "edit" | "confirm"; record: ExpectedRecord };

export function categoryLabel(record: { category?: string | null; subcategory?: string | null }) {
  return [record.category, record.subcategory].filter(Boolean).join(" / ") || "—";
}

export function coverageDurationLabel(record: ExpectedRecord) {
  if (record.coverage_unit == null || record.coverage_interval == null) return "";
  return `${record.coverage_interval} ${record.coverage_unit === "months" ? "个月" : "天"}`;
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
