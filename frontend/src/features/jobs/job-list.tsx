import { Badge, Button, Flex, Select, Text, TextField } from "@radix-ui/themes";
import { Search } from "lucide-react";
import type { JobFilters, JobSummary } from "@/api/jobs";
import { JobError, JobMatchBadge } from "./job-fields";
import { JOB_STATUSES, jobStatusColor, MATCH_LEVELS } from "./job-options";

type FilterOption = string | { value: string; label: string };

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value?: string | null;
  options: readonly FilterOption[];
  onChange: (value: string) => void;
}) {
  return (
    <Select.Root size="1" value={value ?? "all"} onValueChange={onChange}>
      <Select.Trigger aria-label={label} />
      <Select.Content>
        <Select.Item value="all">{label}</Select.Item>
        {options.map((option) => {
          const item = typeof option === "string" ? { value: option, label: option } : option;
          return (
            <Select.Item key={item.value} value={item.value}>
              {item.label}
            </Select.Item>
          );
        })}
      </Select.Content>
    </Select.Root>
  );
}

export function JobList({
  filters,
  setFilters,
  selected,
  onSelect,
  jobs,
  pending,
  error,
  onRetry,
}: {
  filters: JobFilters;
  setFilters: (value: JobFilters) => void;
  selected: number | null;
  onSelect: (id: number) => void;
  jobs: JobSummary[] | undefined;
  pending: boolean;
  error: Error | null;
  onRetry: () => void;
}) {
  return (
    <section className="jobs-list" aria-label="岗位列表">
      <div className="jobs-filters">
        <TextField.Root
          size="2"
          aria-label="搜索岗位"
          placeholder="职位、公司、城市、平台、JD…"
          maxLength={500}
          value={filters.q ?? ""}
          onChange={(event) => setFilters({ ...filters, q: event.target.value })}
        >
          <TextField.Slot>
            <Search size={15} />
          </TextField.Slot>
        </TextField.Root>
        <Flex gap="2" wrap="wrap">
          <FilterSelect
            label="全部状态"
            value={filters.status}
            options={JOB_STATUSES}
            onChange={(status) =>
              setFilters({ ...filters, status: JOB_STATUSES.find((value) => value === status) })
            }
          />
          <FilterSelect
            label="全部匹配度"
            value={filters.match_level}
            options={MATCH_LEVELS}
            onChange={(match) =>
              setFilters({ ...filters, match_level: MATCH_LEVELS.find((value) => value === match) })
            }
          />
          <FilterSelect
            label="全部渠道"
            value={filters.is_headhunter == null ? null : String(filters.is_headhunter)}
            options={[
              { value: "true", label: "猎头" },
              { value: "false", label: "直招" },
            ]}
            onChange={(value) =>
              setFilters({
                ...filters,
                is_headhunter: value === "all" ? undefined : value === "true",
              })
            }
          />
        </Flex>
      </div>
      {pending ? (
        <p className="loading-message" role="status">
          正在读取岗位…
        </p>
      ) : error ? (
        <div className="jobs-list-message">
          <JobError error={error} />
          <Button size="1" variant="soft" onClick={onRetry}>
            重试
          </Button>
        </div>
      ) : jobs?.length ? (
        <ul className="jobs-list-results">
          {jobs.map((job) => (
            <li key={job.id}>
              <button
                type="button"
                aria-pressed={job.id === selected}
                className="jobs-list-item"
                onClick={() => onSelect(job.id)}
              >
                <span className="jobs-list-role">{job.role}</span>
                <span className="jobs-list-company">
                  {[job.company || "公司未确认", job.city, job.salary].filter(Boolean).join(" · ")}
                </span>
                <span className="jobs-list-badges">
                  <Badge color={jobStatusColor(job.status)}>{job.status}</Badge>
                  {job.is_headhunter && <Badge color="gray">猎头</Badge>}
                  <JobMatchBadge analysis={job.latest_analysis} />
                </span>
                <Text size="1" color="gray">
                  {job.encounter_count} 次遇见
                  {job.latest_encounter_date && ` · ${job.latest_encounter_date}`}
                  {job.analysis_stale && " · 分析待更新"}
                </Text>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="jobs-list-message muted-text">
          {Object.values(filters).some(
            (value) => value !== "" && value !== undefined && value !== null,
          )
            ? "没有符合筛选条件的岗位。"
            : "还没有岗位，切到「评估 JD」录入第一份。"}
        </p>
      )}
    </section>
  );
}
