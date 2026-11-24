import type { QueryClient } from "@tanstack/react-query";

export function invalidateFinance(client: QueryClient) {
  return Promise.all(
    [["ledger"], ["capture"]].map((queryKey) => client.invalidateQueries({ queryKey })),
  );
}

export function invalidateMeals(client: QueryClient) {
  return Promise.all(
    [["diet"], ["capture"]].map((queryKey) => client.invalidateQueries({ queryKey })),
  );
}

export function invalidateCapture(client: QueryClient) {
  return Promise.all(
    [["capture"], ["ledger"], ["diet"]].map((queryKey) => client.invalidateQueries({ queryKey })),
  );
}
