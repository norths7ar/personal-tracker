import { Button, Flex } from "@radix-ui/themes";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { jobsApi, type JobDetail, type JobFilters, type JobIntake } from "@/api/jobs";
import { cn } from "@/lib/utils";
import { JobDetailPanel } from "./job-detail";
import { JobError } from "./job-fields";
import { JobEvaluateWorkspace } from "./job-intake";
import { JobList } from "./job-list";
import { createComposeDraft, JOB_POLL_INTERVAL, type ComposeDraft } from "./job-options";
import { JobProfilePanel } from "./job-profile";
import "./jobs-page.css";

type JobsTab = "evaluate" | "library" | "profile";

const TABS: readonly { value: JobsTab; label: string }[] = [
  { value: "evaluate", label: "评估 JD" },
  { value: "library", label: "岗位库" },
  { value: "profile", label: "求职资料" },
];

function parseTab(value: string | null): JobsTab {
  return value === "library" || value === "profile" ? value : "evaluate";
}

export function JobsPage() {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const activeTab = parseTab(params.get("tab"));

  const [filters, setFilters] = useState<JobFilters>({});
  const [selected, setSelected] = useState<number | null>(null);
  const [showListOnMobile, setShowListOnMobile] = useState(false);

  const [composeDraft, setComposeDraft] = useState<ComposeDraft>(createComposeDraft);
  const [activeIntake, setActiveIntake] = useState<JobIntake | null>(null);
  const [evaluatedJobId, setEvaluatedJobId] = useState<number | null>(null);

  function selectTab(tab: JobsTab) {
    if (tab === activeTab) return;
    const next = new URLSearchParams(params);
    if (tab === "evaluate") next.delete("tab");
    else next.set("tab", tab);
    setParams(next);
  }

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

  const detailId = selected ?? jobs.data?.[0]?.id ?? null;

  const detail = useQuery({
    queryKey: ["jobs", "detail", detailId],
    queryFn: () => (detailId === null ? null : jobsApi.detail(detailId)),
    enabled: activeTab === "library" && detailId !== null,
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

  function receiveEvaluated(value: JobDetail) {
    receiveJob(value);
    setSelected(value.id);
    setActiveIntake(null);
    setEvaluatedJobId(value.id);
  }

  function refreshIntakes() {
    void queryClient.invalidateQueries({ queryKey: ["jobs", "intakes"] });
  }

  function removeIntake(id: number) {
    setActiveIntake((current) => (current?.id === id ? null : current));
    queryClient.setQueryData<JobIntake[]>(["jobs", "intakes"], (list) =>
      list?.filter((item) => item.id !== id),
    );
    refreshIntakes();
  }

  return (
    <section className="page-stack jobs-page">
      <header className="page-heading">
        <h1 className="page-title">求职</h1>
      </header>

      <div className="page-tabs jobs-tabs" aria-label="求职视图">
        {TABS.map((item) => (
          <button
            key={item.value}
            type="button"
            className={cn("page-tab", activeTab === item.value && "page-tab-selected")}
            aria-pressed={activeTab === item.value}
            onClick={() => selectTab(item.value)}
          >
            {item.label}
            {item.value === "evaluate" && intakes.data?.length ? ` (${intakes.data.length})` : ""}
          </button>
        ))}
      </div>

      {activeTab === "evaluate" && (
        <JobEvaluateWorkspace
          draft={composeDraft}
          setDraft={setComposeDraft}
          activeIntake={activeIntake}
          evaluatedJobId={evaluatedJobId}
          intakes={intakes.data}
          intakesError={intakes.error}
          onRetryIntakes={() => void intakes.refetch()}
          onSelectIntake={(intake) => {
            setEvaluatedJobId(null);
            setActiveIntake(intake);
          }}
          onClearIntake={() => setActiveIntake(null)}
          onEvaluated={receiveEvaluated}
          onResetEvaluation={() => {
            setEvaluatedJobId(null);
            setActiveIntake(null);
          }}
          onUpdateJob={receiveJob}
          onChangeIntakes={refreshIntakes}
          onDiscardIntake={removeIntake}
          onOpenProfile={() => selectTab("profile")}
          onOpenLibrary={(jobId) => {
            setSelected(jobId);
            setShowListOnMobile(false);
            selectTab("library");
          }}
        />
      )}

      {activeTab === "library" && (
        <div
          className={cn(
            "jobs-workspace",
            detailId !== null && !showListOnMobile && "jobs-workspace-selected",
          )}
        >
          <JobList
            filters={filters}
            setFilters={setFilters}
            selected={detailId}
            onSelect={(id) => {
              setSelected(id);
              setShowListOnMobile(false);
            }}
            jobs={jobs.data}
            pending={jobs.isPending}
            error={jobs.error}
            onRetry={() => void jobs.refetch()}
          />
          <div className="jobs-detail-area">
            {detailId === null ? (
              <div className="empty-panel">
                还没有已保存的岗位，可以在「评估 JD」中贴入第一份岗位信息。
              </div>
            ) : (
              <>
                <Button
                  className="jobs-back"
                  size="2"
                  variant="ghost"
                  onClick={() => setShowListOnMobile(true)}
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
      )}

      {activeTab === "profile" && <JobProfilePanel />}
    </section>
  );
}
