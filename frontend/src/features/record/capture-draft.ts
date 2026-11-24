import { useSyncExternalStore } from "react";
import { today } from "./entry-shared";

const storageKey = "personal-tracker.capture-draft.v1";
type Submission = { text: string; date: string; key: string };
type Draft = { text: string; date: string; pending: Submission | null };
type Snapshot = { draft: Draft; storageError: string | null };
const listeners = new Set<() => void>();
let snapshot: Snapshot | undefined;

function read(): Snapshot {
  const empty: Draft = { text: "", date: today(), pending: null };
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return { draft: empty, storageError: null };
    const saved = JSON.parse(raw) as Partial<Draft>;
    if (typeof saved.text !== "string" || typeof saved.date !== "string") throw new Error();
    const pending = saved.pending;
    return {
      draft: {
        text: saved.text,
        date: saved.date,
        pending:
          pending &&
          typeof pending.text === "string" &&
          typeof pending.date === "string" &&
          typeof pending.key === "string"
            ? pending
            : null,
      },
      storageError: null,
    };
  } catch {
    return { draft: empty, storageError: "无法读取本机草稿，请检查浏览器存储权限。" };
  }
}

function current(): Snapshot {
  snapshot ??= read();
  return snapshot;
}

function latest(): Snapshot {
  if (snapshot?.storageError) return snapshot;
  snapshot = read();
  return snapshot;
}

function write(draft: Draft) {
  let storageError: string | null = null;
  try {
    localStorage.setItem(storageKey, JSON.stringify(draft));
  } catch {
    storageError = "草稿暂时无法保存在本机，请勿刷新或关闭页面。";
  }
  snapshot = { draft, storageError };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const before = current();
  const next = latest();
  if (JSON.stringify(before) !== JSON.stringify(next)) listener();
  const onStorage = (event: StorageEvent) => {
    if (event.key === storageKey || event.key === null) {
      snapshot = read();
      listener();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function useCaptureDraft() {
  return useSyncExternalStore(subscribe, current);
}

export function updateCaptureDraft(changes: Partial<Pick<Draft, "text" | "date">>) {
  write({ ...latest().draft, ...changes });
}

export function beginCaptureSubmission(): Submission {
  const draft = latest().draft;
  if (draft.pending) return draft.pending;
  const pending = { text: draft.text, date: draft.date, key: crypto.randomUUID() };
  write({ ...draft, pending });
  return pending;
}

export function completeCaptureSubmission(key: string) {
  const draft = latest().draft;
  if (draft.pending?.key !== key) return;
  const unchanged = draft.text === draft.pending.text && draft.date === draft.pending.date;
  write({
    text: unchanged ? "" : draft.text,
    date: unchanged ? today() : draft.date,
    pending: null,
  });
}
