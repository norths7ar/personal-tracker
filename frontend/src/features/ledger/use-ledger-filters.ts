import type { Transaction } from "@/api/client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { unique } from "./utils";
export function useLedgerFilters(allRows: Transaction[]) {
  const [params, setParams] = useSearchParams();
  const typeFilter = params.get("type") || "全部";
  const categoryFilter = params.get("category") || "全部";
  const subcategoryFilter = params.get("subcategory") || "全部";
  const search = params.get("q") || "";
  const startDate = params.get("from") || "";
  const endDate = params.get("to") || "";
  const coveredOnly = params.get("covered") === "1";
  const [dateResetKey, setDateResetKey] = useState(0);
  const invalidRange = Boolean(startDate && endDate && startDate > endDate);
  const searchInput = useRef<HTMLInputElement>(null);
  const composingRef = useRef(false);
  const [searchDraft, setSearchDraft] = useState(search);
  const [lastSearch, setLastSearch] = useState(search);
  if (lastSearch !== search) {
    setLastSearch(search);
    setSearchDraft(search);
  }
  const updateFilters = (changes: Record<string, string>) => {
    if ("from" in changes || "to" in changes) setDateResetKey((key) => key + 1);
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        Object.entries(changes).forEach(([key, value]) => {
          if (value && value !== "全部") next.set(key, value);
          else next.delete(key);
        });
        return next;
      },
      { replace: true },
    );
  };
  const selectMonth = (offset: number) => {
    const now = new Date();
    const first = new Date(now.getFullYear(), now.getMonth() + offset, 1);
    const last = new Date(first.getFullYear(), first.getMonth() + 1, 0);
    const format = (value: Date) =>
      `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
    updateFilters({ from: format(first), to: format(last) });
  };
  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        event.key !== "/" ||
        event.ctrlKey ||
        event.altKey ||
        event.metaKey ||
        event.isComposing ||
        document.querySelector('[role="dialog"]') ||
        (target instanceof HTMLElement &&
          (target.closest("input, textarea, select") || target.isContentEditable))
      )
        return;
      event.preventDefault();
      searchInput.current?.focus();
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);
  const filteredRows = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return allRows.filter((row) => {
      if (invalidRange || (startDate && row.date < startDate) || (endDate && row.date > endDate))
        return false;
      if (typeFilter !== "全部" && row.type !== typeFilter) return false;
      if (categoryFilter !== "全部" && row.category !== categoryFilter) return false;
      if (subcategoryFilter !== "全部" && row.subcategory !== subcategoryFilter) return false;
      if (coveredOnly && (!row.coverage_start || !row.coverage_end)) return false;
      if (!needle) return true;
      return [row.description, row.category, row.subcategory, row.notes]
        .filter(Boolean)
        .some((value) => value!.toLocaleLowerCase().includes(needle));
    });
  }, [
    allRows,
    categoryFilter,
    search,
    subcategoryFilter,
    typeFilter,
    startDate,
    endDate,
    invalidRange,
    coveredOnly,
  ]);

  const categoryOptions = useMemo(() => {
    const source =
      typeFilter === "全部" ? allRows : allRows.filter((row) => row.type === typeFilter);
    return unique(source.map((row) => row.category));
  }, [allRows, typeFilter]);
  const subcategoryOptions = useMemo(() => {
    return unique(
      allRows
        .filter((row) => typeFilter === "全部" || row.type === typeFilter)
        .filter((row) => categoryFilter === "全部" || row.category === categoryFilter)
        .map((row) => row.subcategory),
    );
  }, [allRows, categoryFilter, typeFilter]);

  return {
    filteredRows,
    categoryFilter,
    search,
    subcategoryFilter,
    typeFilter,
    startDate,
    endDate,
    coveredOnly,
    categoryOptions,
    subcategoryOptions,
    searchInput,
    searchDraft,
    setSearchDraft,
    composingRef,
    updateFilters,
    dateResetKey,
    invalidRange,
    selectMonth,
  };
}
