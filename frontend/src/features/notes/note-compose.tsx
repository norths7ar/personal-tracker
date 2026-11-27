import { Button, Flex, Text, TextArea, TextField } from "@radix-ui/themes";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { notesApi, type EventDateRange, type NoteItem } from "@/api/notes";
import { DateInput } from "@/components/ui/date-input";
import { EventDatesEditor } from "./event-dates-editor";

const DRAFT_KEY = "personal-tracker:notes-compose-draft:v1";

type Draft = {
  title: string;
  content: string;
  recordedDate: string | null;
  eventDates: EventDateRange[];
};

const today = () => new Intl.DateTimeFormat("en-CA").format(new Date());

function loadDraft(): Draft {
  const fallback: Draft = {
    title: "",
    content: "",
    recordedDate: null,
    eventDates: [],
  };
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<Draft> & { dateCustomized?: boolean };
    const title = typeof parsed.title === "string" ? parsed.title : "";
    const content = typeof parsed.content === "string" ? parsed.content : "";
    const eventDates = Array.isArray(parsed.eventDates) ? parsed.eventDates : [];
    const hasContent = Boolean(title || content || eventDates.length);
    const recordedDate =
      typeof parsed.recordedDate === "string" &&
      parsed.recordedDate &&
      (hasContent || parsed.dateCustomized === true)
        ? parsed.recordedDate
        : null;
    return { title, content, recordedDate, eventDates };
  } catch {
    return fallback;
  }
}

function clearStoredDraft() {
  try {
    window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    // Ignore storage quota / privacy mode errors.
  }
}

export function NoteCompose({
  onSaved,
  onOpenLibrary,
}: {
  onSaved: (note: NoteItem) => void;
  onOpenLibrary: (noteId: number) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>(loadDraft);
  const [todayDate, setTodayDate] = useState(today);
  const [lastSavedId, setLastSavedId] = useState<number | null>(null);
  const effectiveDate = draft.recordedDate ?? todayDate;

  useEffect(() => {
    const refreshToday = () => setTodayDate(today());
    const onVisibility = () => {
      if (document.visibilityState === "visible") refreshToday();
    };
    window.addEventListener("focus", refreshToday);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("focus", refreshToday);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  useEffect(() => {
    const hasDraft = Boolean(
      draft.title || draft.content || draft.eventDates.length || draft.recordedDate !== null,
    );
    if (!hasDraft) {
      clearStoredDraft();
      return;
    }
    try {
      window.localStorage.setItem(
        DRAFT_KEY,
        JSON.stringify({ ...draft, dateCustomized: draft.recordedDate !== null }),
      );
    } catch {
      // Ignore storage quota / privacy mode errors.
    }
  }, [draft]);

  const create = useMutation({
    mutationFn: notesApi.create,
    onSuccess: (note) => {
      clearStoredDraft();
      setTodayDate(today());
      setDraft({
        title: "",
        content: "",
        recordedDate: null,
        eventDates: [],
      });
      setLastSavedId(note.id);
      void queryClient.invalidateQueries({ queryKey: ["notes"] });
      onSaved(note);
    },
  });

  function submit() {
    if (create.isPending || !draft.content.trim() || !effectiveDate) return;
    create.mutate({
      title: draft.title,
      content: draft.content,
      recorded_date: effectiveDate,
      event_dates: draft.eventDates,
    });
  }

  return (
    <section
      className="content-panel notes-compose"
      aria-label="记录随手记"
      onKeyDown={(event) => {
        if (
          event.defaultPrevented ||
          !event.ctrlKey ||
          event.key !== "Enter" ||
          event.repeat ||
          event.nativeEvent.isComposing
        ) {
          return;
        }
        event.preventDefault();
        submit();
      }}
    >
      <form
        className="notes-fields"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <fieldset className="notes-fields" disabled={create.isPending}>
          <div className="notes-compose-top">
            <label className="notes-field notes-compose-title">
              <Text size="2" weight="medium">
                标题（可选）
              </Text>
              <TextField.Root
                maxLength={200}
                placeholder="简短概括，或留空按日期归档"
                value={draft.title}
                onChange={(event) => {
                  const title = event.target.value;
                  setDraft((current) => ({ ...current, title }));
                }}
              />
            </label>
            <label className="notes-field notes-compose-recorded">
              <Text size="2" weight="medium">
                记录日期
              </Text>
              <DateInput
                required
                value={effectiveDate}
                onChange={(event) => {
                  const value = event.target.value;
                  setDraft((current) => ({ ...current, recordedDate: value || null }));
                }}
              />
            </label>
          </div>
          <label className="notes-field">
            <Text size="2" weight="medium">
              正文
            </Text>
            <TextArea
              autoFocus
              required
              rows={11}
              placeholder="随手写一段话或生活切片，支持 Markdown；Ctrl + Enter 保存"
              value={draft.content}
              onChange={(event) => {
                const content = event.target.value;
                setDraft((current) => ({ ...current, content }));
              }}
            />
          </label>
          <EventDatesEditor
            value={draft.eventDates}
            onChange={(eventDates) => setDraft((current) => ({ ...current, eventDates }))}
          />
        </fieldset>

        {create.error && (
          <Text as="p" size="2" color="red" role="alert">
            {create.error.message}
          </Text>
        )}

        <Flex align="center" justify="between" gap="3" wrap="wrap">
          <div>
            {lastSavedId !== null && !draft.content && (
              <Flex align="center" gap="2">
                <Text size="2" color="gray" role="status">
                  已保存
                </Text>
                <Button
                  type="button"
                  size="1"
                  variant="soft"
                  onClick={() => onOpenLibrary(lastSavedId)}
                >
                  去查看
                </Button>
              </Flex>
            )}
          </div>
          <Button
            type="submit"
            loading={create.isPending}
            disabled={create.isPending || !draft.content.trim() || !effectiveDate}
          >
            保存随手记
          </Button>
        </Flex>
      </form>
    </section>
  );
}
