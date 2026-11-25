import { request } from "./client";
import type { components, paths } from "./schema";

type Schemas = components["schemas"];
export type EventDateRange = Schemas["EventDateRange"];
export type NoteItem = Schemas["NoteItem"];
export type NotesListResponse = Schemas["NotesListResponse"];
export type NoteCreate = Schemas["NoteCreate"];
export type NoteUpdate = Schemas["NoteUpdate"];
export type NoteFilters = NonNullable<paths["/api/notes"]["get"]["parameters"]["query"]>;

export function formatEventRange(item: EventDateRange) {
  return item.start_date === item.end_date
    ? item.start_date
    : `${item.start_date} 至 ${item.end_date}`;
}

export const notesApi = {
  list: (filters: NoteFilters) => {
    const query = new URLSearchParams();
    if (filters.year) query.set("year", filters.year);
    if (filters.q?.trim()) query.set("q", filters.q.trim());
    if (filters.sort) query.set("sort", filters.sort);
    return request<NotesListResponse>(`/api/notes${query.size ? `?${query}` : ""}`);
  },
  create: (body: NoteCreate) =>
    request<NoteItem>("/api/notes", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: number, body: NoteUpdate) =>
    request<NoteItem>(`/api/notes/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (id: number) => request<void>(`/api/notes/${id}`, { method: "DELETE" }),
  exportUrl: (format: "md" | "docx", filters: { year?: string | null; q?: string }) => {
    const query = new URLSearchParams({ format });
    if (filters.year) query.set("year", filters.year);
    if (filters.q?.trim()) query.set("q", filters.q.trim());
    return `/api/notes/export?${query}`;
  },
};
