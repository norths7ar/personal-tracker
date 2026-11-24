import type { JobAnalysis, JobFields } from "@/api/jobs";

export const JOB_POLL_INTERVAL = 3500;
export const DEFAULT_PLATFORM = "BOSS直聘";
export const JOB_PROFILE_QUERY_KEY = ["jobs", "profile"] as const;

export type ComposeDraft = {
  rawJd: string;
  date: string;
  platform: string;
  customPlatform: string;
  contact: string;
  salary: string;
  notes: string;
  greetingOverride: boolean | null;
};

export function createComposeDraft(): ComposeDraft {
  return {
    rawJd: "",
    date: new Intl.DateTimeFormat("en-CA").format(new Date()),
    platform: DEFAULT_PLATFORM,
    customPlatform: "",
    contact: "",
    salary: "",
    notes: "",
    greetingOverride: null,
  };
}

export const JOB_STATUSES = [
  "待决定",
  "已联系",
  "已跳过",
] as const satisfies readonly JobFields["status"][];

export const MATCH_LEVELS = [
  "高",
  "中高",
  "中",
  "中低",
  "低",
] as const satisfies readonly JobAnalysis["match_level"][];

export const EMPTY_JOB: JobFields = {
  company: "",
  role: "",
  city: "",
  salary: "",
  status: "待决定",
  notes: "",
  is_headhunter: false,
  headhunter_agency: "",
};

export function jobStatusColor(status: JobFields["status"]): "gray" | "jade" {
  return status === "已联系" ? "jade" : "gray";
}

export function editableJob(job: JobFields): JobFields {
  const { company, role, city, salary, status, notes, is_headhunter, headhunter_agency } = job;
  return { company, role, city, salary, status, notes, is_headhunter, headhunter_agency };
}

export function formatJobTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "short",
    timeStyle: "short",
    hour12: false,
  }).format(new Date(value));
}
