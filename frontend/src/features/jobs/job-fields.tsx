import { Badge, Checkbox, Select, Text, TextArea, TextField } from "@radix-ui/themes";
import { useId, type ReactNode } from "react";
import type { JobAnalysis, JobFields } from "@/api/jobs";
import { JOB_STATUSES } from "./job-options";

export function JobField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="jobs-field">
      <Text size="2" weight="medium">
        {label}
      </Text>
      {children}
    </label>
  );
}

export function JobFieldsEditor({
  value,
  onChange,
}: {
  value: JobFields;
  onChange: (value: JobFields) => void;
}) {
  const statusId = useId();
  const set = <K extends keyof JobFields>(field: K, next: JobFields[K]) =>
    onChange({ ...value, [field]: next });

  return (
    <div className="jobs-fields">
      <div className="jobs-fields-grid">
        <JobField label="职位">
          <TextField.Root
            required
            value={value.role}
            onChange={(event) => set("role", event.target.value)}
          />
        </JobField>
        <JobField label="实际招聘公司">
          <TextField.Root
            placeholder="不明确时留空"
            value={value.company}
            onChange={(event) => set("company", event.target.value)}
          />
        </JobField>
        <JobField label="城市">
          <TextField.Root
            value={value.city}
            onChange={(event) => set("city", event.target.value)}
          />
        </JobField>
        <JobField label="岗位薪资">
          <TextField.Root
            value={value.salary}
            onChange={(event) => set("salary", event.target.value)}
          />
        </JobField>
        <div className="jobs-field">
          <Text as="label" size="2" weight="medium" htmlFor={statusId}>
            求职状态
          </Text>
          <Select.Root
            value={value.status}
            onValueChange={(status) => {
              const next = JOB_STATUSES.find((option) => option === status);
              if (next) set("status", next);
            }}
          >
            <Select.Trigger id={statusId} />
            <Select.Content>
              {JOB_STATUSES.map((status) => (
                <Select.Item key={status} value={status}>
                  {status}
                </Select.Item>
              ))}
            </Select.Content>
          </Select.Root>
        </div>
        <label className="jobs-checkbox jobs-headhunter">
          <Checkbox
            checked={value.is_headhunter}
            onCheckedChange={(checked) => set("is_headhunter", checked === true)}
          />
          由猎头发布
        </label>
      </div>
      {(value.is_headhunter || value.headhunter_agency) && (
        <JobField label="猎头机构（不是招聘公司）">
          <TextField.Root
            value={value.headhunter_agency}
            onChange={(event) => set("headhunter_agency", event.target.value)}
          />
        </JobField>
      )}
      <JobField label="岗位备注">
        <TextArea
          rows={3}
          value={value.notes}
          onChange={(event) => set("notes", event.target.value)}
        />
      </JobField>
    </div>
  );
}

export function JobMatchBadge({ analysis }: { analysis: JobAnalysis | null | undefined }) {
  if (!analysis) return <Badge color="gray">未分析</Badge>;
  const level = analysis.match_level;
  const color = level === "高" || level === "中高" ? "jade" : level === "中" ? "gray" : "amber";
  return <Badge color={color}>匹配 · {level}</Badge>;
}

export function JobError({ error }: { error: Error | string | null }) {
  return error ? (
    <Text as="p" size="2" color="red" role="alert">
      {typeof error === "string" ? error : error.message}
    </Text>
  ) : null;
}
