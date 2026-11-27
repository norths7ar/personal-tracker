import { useSyncExternalStore } from "react";
import { today } from "./entry-shared";

const storageKey = "personal-tracker.capture-draft.v1";
type Submission = { text: string; date: string; key: string };
type Draft = { text: string; date: string; dateCustomized: boolean; pending: Submission | null };
type Snapshot = { draft: Draft; storageError: string | null };
const listeners = new Set<() => void>();
let snapshot: Snapshot | undefined;

function read(): Snapshot {
  const currentDay = today();
  const empty: Draft = { text: "", date: currentDay, dateCustomized: false, pending: null };
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return { draft: empty, storageError: null };
    const saved = JSON.parse(raw) as Partial<Draft>;
    if (typeof saved.text !== "string" || typeof saved.date !== "string") throw new Error();
    const pending = saved.pending;
    const validPending =
      pending &&
      typeof pending.text === "string" &&
      typeof pending.date === "string" &&
      typeof pending.key === "string"
        ? pending
        : null;
    const dateCustomized = saved.dateCustomized === true;
    const isIdleDefault = saved.text === "" && validPending === null && !dateCustomized;
    return {
      draft: {
        text: saved.text,
        date: isIdleDefault || !saved.date ? currentDay : saved.date,
        dateCustomized,
        pending: validPending,
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
  const idleDefault = !draft.text && !draft.dateCustomized && draft.pending === null;
  const nextDraft = idleDefault ? { ...draft, date: today() } : draft;
  try {
    if (idleDefault) {
      localStorage.removeItem(storageKey);
    } else {
      localStorage.setItem(storageKey, JSON.stringify(nextDraft));
    }
  } catch {
    storageError = "草稿暂时无法保存在本机，请勿刷新或关闭页面。";
  }
  snapshot = { draft: nextDraft, storageError };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const refresh = () => {
    const before = current();
    const next = latest();
    if (JSON.stringify(before) !== JSON.stringify(next)) listener();
  };
  refresh();
  const onStorage = (event: StorageEvent) => {
    if (event.key === storageKey || event.key === null) {
      snapshot = read();
      listener();
    }
  };
  const onVisibility = () => {
    if (document.visibilityState === "visible") refresh();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener("focus", refresh);
  document.addEventListener("visibilitychange", onVisibility);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
    window.removeEventListener("focus", refresh);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}

export function useCaptureDraft() {
  return useSyncExternalStore(subscribe, current);
}

export function updateCaptureDraft(changes: Partial<Pick<Draft, "text" | "date">>) {
  const prev = latest().draft;
  const dateCustomized = "date" in changes ? true : prev.dateCustomized;
  const date = "date" in changes ? (changes.date ?? today()) : prev.date || today();
  write({ ...prev, ...changes, date, dateCustomized });
}

export function beginCaptureSubmission(): Submission {
  const draft = latest().draft;
  if (draft.pending) return draft.pending;
  const pending = { text: draft.text, date: draft.date || today(), key: crypto.randomUUID() };
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
    dateCustomized: unchanged ? false : draft.dateCustomized,
    pending: null,
  });
}
