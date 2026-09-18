import type { QueryClient } from "@tanstack/react-query";

export function invalidateFinance(client: QueryClient) {
  return Promise.all(
    [
      "transactions",
      "pending-transactions",
      "expense-analysis",
      "cross-period",
      "home-summary",
    ].map((key) => client.invalidateQueries({ queryKey: [key] })),
  );
}

export function invalidateMeals(client: QueryClient) {
  return Promise.all(
    ["meals", "diet-stats", "home-summary"].map((key) =>
      client.invalidateQueries({ queryKey: [key] }),
    ),
  );
}
