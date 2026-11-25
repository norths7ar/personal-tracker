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
  recordedDate: string;
  eventDates: EventDateRange[];
};

const today = () => new Intl.DateTimeFormat("en-CA").format(new Date());

function loadDraft(): Draft {
  const fallback: Draft = {
    title: "",
    content: "",
    recordedDate: today(),
    eventDates: [],
  };
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<Draft>;
    return {
      title: typeof parsed.title === "string" ? parsed.title : "",
      content: typeof parsed.content === "string" ? parsed.content : "",
      recordedDate:
        typeof parsed.recordedDate === "string" && parsed.recordedDate
          ? parsed.recordedDate
          : fallback.recordedDate,
      eventDates: Array.isArray(parsed.eventDates) ? parsed.eventDates : [],
    };
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
  const [lastSavedId, setLastSavedId] = useState<number | null>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch {
      // Ignore storage quota / privacy mode errors.
    }
  }, [draft]);

  const create = useMutation({
    mutationFn: notesApi.create,
    onSuccess: (note) => {
      clearStoredDraft();
      setDraft({
        title: "",
        content: "",
        recordedDate: today(),
        eventDates: [],
      });
      setLastSavedId(note.id);
      void queryClient.invalidateQueries({ queryKey: ["notes"] });
      onSaved(note);
    },
  });

  function submit() {
    if (create.isPending || !draft.content.trim() || !draft.recordedDate) return;
    create.mutate({
      title: draft.title,
      content: draft.content,
      recorded_date: draft.recordedDate,
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
                value={draft.recordedDate}
                onChange={(event) => {
                  const recordedDate = event.target.value;
                  setDraft((current) => ({ ...current, recordedDate }));
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
            disabled={create.isPending || !draft.content.trim() || !draft.recordedDate}
          >
            保存随手记
          </Button>
        </Flex>
      </form>
    </section>
  );
}
