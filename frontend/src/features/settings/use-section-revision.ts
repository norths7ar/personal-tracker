import { useEffect, useRef } from "react";

export function useSectionRevision(
  signature: string,
  revision: string,
  dirty: boolean,
  reset: () => void,
) {
  const baseline = useRef({ signature, revision });
  const resetRef = useRef(reset);
  useEffect(() => {
    resetRef.current = reset;
  }, [reset]);
  useEffect(() => {
    if (baseline.current.signature === signature) {
      baseline.current.revision = revision;
    } else if (!dirty) {
      baseline.current = { signature, revision };
      resetRef.current();
    }
  }, [signature, revision, dirty]);
  return {
    revision: () => baseline.current.revision,
    accept: (nextSignature: string, nextRevision: string) => {
      baseline.current = { signature: nextSignature, revision: nextRevision };
    },
  };
}

export const settingsQueryKey = ["settings"];
