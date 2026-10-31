import { request } from "./client";
import type { components } from "./schema";

export type Settings = components["schemas"]["SettingsResponse"];
export type ModelSettingsUpdate = components["schemas"]["ModelSettingsUpdate"];
export type RecordSettingsUpdate = components["schemas"]["RecordSettingsUpdate"];
export type AccessSettingsUpdate = components["schemas"]["AccessSettingsUpdate"];

export const settingsApi = {
  get: () => request<Settings>("/api/settings"),
  model: (body: ModelSettingsUpdate) =>
    request<Settings>("/api/settings/model", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  records: (body: RecordSettingsUpdate) =>
    request<Settings>("/api/settings/records", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  access: (body: AccessSettingsUpdate) =>
    request<Settings>("/api/settings/access", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};
