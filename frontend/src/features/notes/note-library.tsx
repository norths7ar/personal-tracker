import { Badge, Button, Flex, Heading, Select, Text, TextArea, TextField } from "@radix-ui/themes";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Pencil, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import Markdown from "react-markdown";
import {
  formatEventRange,
  notesApi,
  type EventDateRange,
  type NoteFilters,
  type NoteItem,
} from "@/api/notes";
import { DateInput } from "@/components/ui/date-input";
import { cn } from "@/lib/utils";
import { EventDatesEditor } from "./event-dates-editor";

function noteTitle(note: NoteItem) {
  if (note.title.trim()) return note.title;
  const anchor = note.event_dates[0]?.start_date ?? note.recorded_date;
  return `${anchor} 日记`;
}

function ExportLink({ href, label, disabled }: { href: string; label: string; disabled: boolean }) {
  if (disabled) {
    return (
      <Button size="1" variant="soft" disabled>
        <Download size={13} /> {label}
      </Button>
    );
  }
  return (
    <Button asChild size="1" variant="soft">
      <a href={href} download>
        <Download size={13} /> {label}
      </a>
    </Button>
  );
}

export function NoteLibrary({
  selected,
  onSelect,
}: {
  selected: number | null;
  onSelect: (id: number | null) => void;
}) {
  const [filters, setFilters] = useState<NoteFilters>({ sort: "recorded" });
  const [showListOnMobile, setShowListOnMobile] = useState(false);

  const notesQuery = useQuery({
    queryKey: ["notes", "list", filters],
    queryFn: () => notesApi.list(filters),
    placeholderData: keepPreviousData,
  });

  const items = notesQuery.data?.items ?? [];
  const years = notesQuery.data?.years ?? [];
  const activeId =
    selected !== null && items.some((item) => item.id === selected)
      ? selected
      : (items[0]?.id ?? null);
  const activeNote = items.find((item) => item.id === activeId) ?? null;

  return (
    <div
      className={cn(
        "notes-workspace",
        activeNote !== null && !showListOnMobile && "notes-workspace-selected",
      )}
    >
      <section className="notes-list" aria-label="日记列表">
        <div className="notes-filters">
          <TextField.Root
            size="2"
            aria-label="搜索日记"
            placeholder="搜索标题或正文…"
            maxLength={500}
            value={filters.q ?? ""}
            onChange={(event) => setFilters((current) => ({ ...current, q: event.target.value }))}
          >
            <TextField.Slot>
              <Search size={15} />
            </TextField.Slot>
          </TextField.Root>
          <Flex gap="2" wrap="wrap">
            <Select.Root
              size="1"
              value={filters.year ?? "all"}
              onValueChange={(value) =>
                setFilters((current) => ({
                  ...current,
                  year: value === "all" ? undefined : value,
                }))
              }
            >
              <Select.Trigger aria-label="筛选年份" />
              <Select.Content>
                <Select.Item value="all">全部年份</Select.Item>
                {years.map((year) => (
                  <Select.Item key={year} value={year}>
                    {year} 年
                  </Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
            <Select.Root
              size="1"
              value={filters.sort ?? "recorded"}
              onValueChange={(value) =>
                setFilters((current) => ({
                  ...current,
                  sort: value === "event" ? "event" : "recorded",
                }))
              }
            >
              <Select.Trigger aria-label="排序方式" />
              <Select.Content>
                <Select.Item value="recorded">按记录日期</Select.Item>
                <Select.Item value="event">按事件日期</Select.Item>
              </Select.Content>
            </Select.Root>
          </Flex>
          <Flex gap="2" wrap="wrap">
            <ExportLink
              href={notesApi.exportUrl("md", filters)}
              label="导出 MD"
              disabled={!items.length}
            />
            <ExportLink
              href={notesApi.exportUrl("docx", filters)}
              label="导出 DOCX"
              disabled={!items.length}
            />
          </Flex>
        </div>

        {notesQuery.isPending ? (
          <p className="loading-message" role="status">
            正在读取日记…
          </p>
        ) : notesQuery.isError ? (
          <div className="notes-list-message">
            <Text size="2" color="red" role="alert">
              {notesQuery.error.message}
            </Text>
            <Button size="1" variant="soft" onClick={() => void notesQuery.refetch()}>
              重试
            </Button>
          </div>
        ) : items.length ? (
          <ul className="notes-list-results">
            {items.map((item) => {
              const firstEvent = item.event_dates[0];
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className="notes-list-item"
                    aria-pressed={item.id === activeId}
                    onClick={() => {
                      onSelect(item.id);
                      setShowListOnMobile(false);
                    }}
                  >
                    <span className="notes-list-title">{noteTitle(item)}</span>
                    <Text size="1" color="gray">
                      记录 {item.recorded_date}
                      {firstEvent && ` · 事件 ${formatEventRange(firstEvent)}`}
                      {item.event_dates.length > 1 && ` 等 ${item.event_dates.length} 项`}
                    </Text>
                    <span className="notes-list-preview">{item.content}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="notes-list-message muted-text">
            {filters.year || filters.q?.trim()
              ? "没有符合条件的日记。"
              : "还没有日记，切到「记录」写第一篇。"}
          </p>
        )}
      </section>

      <div className="notes-detail-area">
        {activeNote === null ? (
          <div className="empty-panel">
            {filters.year || filters.q?.trim()
              ? "没有符合筛选条件的日记。"
              : "还没有已保存的日记。"}
          </div>
        ) : (
          <>
            <Button
              className="notes-back"
              size="2"
              variant="ghost"
              onClick={() => setShowListOnMobile(true)}
            >
              返回列表
            </Button>
            <NoteDetailPanel
              key={activeNote.id}
              note={activeNote}
              onDeleted={() => {
                if (selected === activeNote.id) onSelect(null);
              }}
            />
          </>
        )}
      </div>
    </div>
  );
}

function NoteDetailPanel({ note, onDeleted }: { note: NoteItem; onDeleted: () => void }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(note.title);
  const [content, setContent] = useState(note.content);
  const [recordedDate, setRecordedDate] = useState(note.recorded_date);
  const [eventDates, setEventDates] = useState<EventDateRange[]>(note.event_dates);

  const update = useMutation({
    mutationFn: () =>
      notesApi.update(note.id, {
        title,
        content,
        recorded_date: recordedDate,
        event_dates: eventDates,
      }),
    onSuccess: () => {
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["notes"] });
    },
  });

  const remove = useMutation({
    mutationFn: () => notesApi.remove(note.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notes"] });
      onDeleted();
    },
  });

  function startEdit() {
    setTitle(note.title);
    setContent(note.content);
    setRecordedDate(note.recorded_date);
    setEventDates(note.event_dates);
    update.reset();
    setEditing(true);
  }

  return (
    <section className="notes-detail" aria-labelledby="notes-detail-heading">
      {editing ? (
        <form
          className="notes-fields notes-detail-body"
          onSubmit={(event) => {
            event.preventDefault();
            if (!update.isPending && content.trim() && recordedDate) {
              update.mutate();
            }
          }}
        >
          <fieldset className="notes-fields" disabled={update.isPending}>
            <div className="notes-compose-top">
              <label className="notes-field notes-compose-title">
                <Text size="2" weight="medium">
                  标题（可选）
                </Text>
                <TextField.Root
                  maxLength={200}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              <label className="notes-field notes-compose-recorded">
                <Text size="2" weight="medium">
                  记录日期
                </Text>
                <DateInput
                  required
                  value={recordedDate}
                  onChange={(event) => setRecordedDate(event.target.value)}
                />
              </label>
            </div>
            <label className="notes-field">
              <Text size="2" weight="medium">
                正文
              </Text>
              <TextArea
                rows={12}
                required
                value={content}
                onChange={(event) => setContent(event.target.value)}
              />
            </label>
            <EventDatesEditor value={eventDates} onChange={setEventDates} />
          </fieldset>
          {update.error && (
            <Text as="p" size="2" color="red" role="alert">
              {update.error.message}
            </Text>
          )}
          <Flex justify="end" gap="2" wrap="wrap">
            <Button
              type="button"
              variant="soft"
              disabled={update.isPending}
              onClick={() => setEditing(false)}
            >
              取消
            </Button>
            <Button
              type="submit"
              loading={update.isPending}
              disabled={update.isPending || !content.trim() || !recordedDate}
            >
              保存修改
            </Button>
          </Flex>
        </form>
      ) : (
        <>
          <header className="notes-detail-header">
            <div className="notes-detail-meta">
              <Heading as="h2" size="5" id="notes-detail-heading">
                {noteTitle(note)}
              </Heading>
              <Flex gap="2" align="center" wrap="wrap">
                <Text size="2" color="gray">
                  记录日期：{note.recorded_date}
                </Text>
                {note.event_dates.map((item) => (
                  <Badge key={`${item.start_date}:${item.end_date}`} color="gray" size="1">
                    事件：{formatEventRange(item)}
                  </Badge>
                ))}
              </Flex>
            </div>
            <Flex gap="2" wrap="wrap">
              <Button size="2" variant="outline" onClick={startEdit} disabled={remove.isPending}>
                <Pencil size={14} /> 编辑
              </Button>
              <Button
                size="2"
                variant="soft"
                color="red"
                loading={remove.isPending}
                onClick={() => {
                  if (window.confirm("确认删除这篇日记？")) {
                    remove.mutate();
                  }
                }}
              >
                <Trash2 size={14} /> 删除
              </Button>
            </Flex>
          </header>
          {remove.error && (
            <div className="notes-detail-error">
              <Text as="p" size="2" color="red" role="alert">
                {remove.error.message}
              </Text>
            </div>
          )}
          <div className="notes-detail-body notes-markdown">
            <Markdown skipHtml disallowedElements={["img"]}>
              {note.content}
            </Markdown>
          </div>
        </>
      )}
    </section>
  );
}
