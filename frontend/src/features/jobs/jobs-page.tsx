import { Badge, Button, Flex, Heading, Text } from "@radix-ui/themes";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Plus } from "lucide-react";
import { useState } from "react";
import { jobsApi, type JobDetail, type JobFilters, type JobIntake } from "@/api/jobs";
import { JobDetailPanel } from "./job-detail";
import { JobError } from "./job-fields";
import { JobIntakeDialog } from "./job-intake";
import { JobList } from "./job-list";
import { JOB_POLL_INTERVAL } from "./job-options";
import { JobProfileDialog } from "./job-profile";
import "./jobs-page.css";

export function JobsPage() {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<JobFilters>({});
  const [selected, setSelected] = useState<number | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [pendingIntake, setPendingIntake] = useState<JobIntake | null>(null);
  const jobs = useQuery({
    queryKey: ["jobs", "list", filters],
    queryFn: () => jobsApi.list(filters),
    placeholderData: keepPreviousData,
  });
  const intakes = useQuery({
    queryKey: ["jobs", "intakes"],
    queryFn: jobsApi.intakes,
    refetchInterval: ({ state: { data } }) =>
      data?.some((item) => item.status === "pending") ? JOB_POLL_INTERVAL : false,
  });
  const detail = useQuery({
    queryKey: ["jobs", "detail", selected],
    queryFn: () => (selected === null ? null : jobsApi.detail(selected)),
    enabled: selected !== null,
    refetchInterval: ({ state: { data } }) =>
      data?.analysis_status === "pending" ||
      data?.unfinished_questions.some((item) => item.status === "pending")
        ? JOB_POLL_INTERVAL
        : false,
  });

  function receiveJob(value: JobDetail) {
    queryClient.setQueryData(["jobs", "detail", value.id], value);
    void queryClient.invalidateQueries({ queryKey: ["jobs", "list"] });
  }

  function receiveIntake(value: JobDetail) {
    receiveJob(value);
    setSelected(value.id);
    setIntakeOpen(false);
    setPendingIntake(null);
  }

  function refreshIntakes() {
    void queryClient.invalidateQueries({ queryKey: ["jobs", "intakes"] });
  }

  function removeIntake(id: number) {
    queryClient.setQueryData<JobIntake[]>(["jobs", "intakes"], (intakes) =>
      intakes?.filter((intake) => intake.id !== id),
    );
    refreshIntakes();
  }

  return (
    <section className="jobs-page">
      <header className="page-heading">
        <Heading as="h1" className="page-title" size="7">
          求职
        </Heading>
        <Flex gap="2" wrap="wrap">
          <Button variant="outline" onClick={() => setProfileOpen(true)}>
            <FileText size={16} /> 求职资料
          </Button>
          <Button onClick={() => setIntakeOpen(true)}>
            <Plus size={16} /> 录入 JD
          </Button>
        </Flex>
      </header>

      {intakes.isError && (
        <Flex align="center" gap="2" wrap="wrap">
          <JobError error={`未能读取待确认的 JD：${intakes.error.message}`} />
          <Button size="1" variant="soft" onClick={() => void intakes.refetch()}>
            重试
          </Button>
        </Flex>
      )}
      {!!intakes.data?.length && (
        <section aria-label="待确认的 JD" className="jobs-pending">
          <Text size="2" weight="medium">
            待确认的 JD
          </Text>
          {intakes.data.map((intake) => (
            <Button
              key={intake.id}
              size="1"
              variant="soft"
              color="gray"
              onClick={() => setPendingIntake(intake)}
            >
              {intake.fields?.role || `${intake.encounter.date} · ${intake.encounter.platform}`}
              {intake.status === "failed" && (
                <Badge color="amber" size="1">
                  提取失败
                </Badge>
              )}
            </Button>
          ))}
        </section>
      )}

      <div className={`jobs-workspace${selected !== null ? " jobs-workspace-selected" : ""}`}>
        <JobList
          filters={filters}
          setFilters={setFilters}
          selected={selected}
          onSelect={setSelected}
          jobs={jobs.data}
          pending={jobs.isPending}
          error={jobs.error}
          onRetry={() => void jobs.refetch()}
        />
        <div className="jobs-detail-area">
          {selected === null ? (
            <p className="jobs-placeholder">选择岗位查看详情</p>
          ) : (
            <>
              <Button
                className="jobs-back"
                size="2"
                variant="ghost"
                onClick={() => setSelected(null)}
              >
                返回岗位列表
              </Button>
              {detail.isPending && (
                <p className="loading-message" role="status">
                  正在读取岗位…
                </p>
              )}
              {detail.isError && (
                <Flex align="center" gap="2" wrap="wrap">
                  <JobError error={detail.error} />
                  <Button size="1" variant="soft" onClick={() => void detail.refetch()}>
                    重试
                  </Button>
                </Flex>
              )}
              {detail.data && (
                <JobDetailPanel key={detail.data.id} job={detail.data} onUpdate={receiveJob} />
              )}
            </>
          )}
        </div>
      </div>

      <JobProfileDialog open={profileOpen} onClose={() => setProfileOpen(false)} />
      <JobIntakeDialog
        open={intakeOpen}
        seed={null}
        onClose={() => setIntakeOpen(false)}
        onChange={refreshIntakes}
        onDiscard={removeIntake}
        onSave={receiveIntake}
      />
      {pendingIntake && (
        <JobIntakeDialog
          key={pendingIntake.id}
          open
          seed={pendingIntake}
          onClose={() => setPendingIntake(null)}
          onChange={refreshIntakes}
          onDiscard={removeIntake}
          onSave={receiveIntake}
        />
      )}
    </section>
  );
}
