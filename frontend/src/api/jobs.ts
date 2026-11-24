import { request } from "./client";
import type { components, paths } from "./schema";

type Schemas = components["schemas"];
type JobProfile = Schemas["Profile"];
export type JobFields = Schemas["JobFields"];
export type JobDetail = Schemas["JobDetail"];
export type JobSummary = Schemas["JobSummary"];
export type JobAnalysis = Schemas["Analysis"];
export type EncounterInput = Schemas["EncounterInput"];
export type JobIntake = Schemas["Intake"];
export type IntakeCreate = Schemas["IntakeCreate"];
export type IntakeSave = Schemas["IntakeSave"];
export type JobFilters = NonNullable<paths["/api/jobs"]["get"]["parameters"]["query"]>;

function write<T>(path: string, method: "POST" | "PUT" | "PATCH", body: unknown) {
  return request<T>(`/api/jobs${path}`, { method, body: JSON.stringify(body) });
}

export const jobsApi = {
  list: (filters: JobFilters) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value === null || value === undefined) continue;
      const text = String(value).trim();
      if (text) query.set(key, text);
    }
    return request<JobSummary[]>(`/api/jobs${query.size ? `?${query}` : ""}`);
  },
  detail: (id: number) => request<JobDetail>(`/api/jobs/${id}`),
  update: (id: number, body: Schemas["JobUpdate"]) => write<JobDetail>(`/${id}`, "PATCH", body),
  intakes: () => request<JobIntake[]>("/api/jobs/intakes"),
  intake: (id: number) => request<JobIntake>(`/api/jobs/intakes/${id}`),
  discardIntake: (id: number) => request<void>(`/api/jobs/intakes/${id}`, { method: "DELETE" }),
  prepare: (body: IntakeCreate) => write<JobIntake>("/intakes", "POST", body),
  retryIntake: (id: number) =>
    request<JobIntake>(`/api/jobs/intakes/${id}/retry`, { method: "POST" }),
  saveIntake: (id: number, body: IntakeSave) =>
    write<JobDetail>(`/intakes/${id}/save`, "POST", body),
  analyze: (id: number, body: Schemas["AnalysisRequest"]) =>
    write<JobDetail>(`/${id}/analysis`, "POST", body),
  ask: (id: number, body: Schemas["QuestionRequest"]) =>
    write<JobDetail>(`/${id}/questions`, "POST", body),
  context: (id: number) => request<Schemas["Context"]>(`/api/jobs/${id}/context`),
  profile: () => request<JobProfile>("/api/jobs/profile"),
  saveProfile: (body: Schemas["ProfileWrite"]) => write<JobProfile>("/profile", "PUT", body),
  previewDocx: (file: File) =>
    request<Schemas["DocxPreview"]>(
      `/api/jobs/profile/docx?${new URLSearchParams({ filename: file.name })}`,
      {
        method: "POST",
        body: file,
        headers: {
          "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
      },
    ),
};
