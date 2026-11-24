import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export function useCapturePending() {
  return useQuery({
    queryKey: ["capture", "pending"],
    queryFn: api.capturePending,
    refetchInterval: (query) => (query.state.data?.processing_count ? 1500 : 5000),
  });
}
