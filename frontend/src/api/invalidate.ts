import type { QueryClient } from "@tanstack/react-query";

export function invalidateFinance(client: QueryClient) {
  return Promise.all(
    [["ledger"], ["capture", "home"]].map((queryKey) => client.invalidateQueries({ queryKey })),
  );
}

export function invalidateMeals(client: QueryClient) {
  return Promise.all(
    [["diet"], ["capture", "home"]].map((queryKey) => client.invalidateQueries({ queryKey })),
  );
}
