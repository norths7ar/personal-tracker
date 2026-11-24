import type { JobAnalysis, JobFields } from "@/api/jobs";

export const JOB_POLL_INTERVAL = 3500;

export const JOB_STATUSES = [
  "待看",
  "已沟通",
  "已投递",
  "面试中",
  "已放弃",
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
  status: "待看",
  notes: "",
  is_headhunter: false,
  headhunter_agency: "",
};

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
