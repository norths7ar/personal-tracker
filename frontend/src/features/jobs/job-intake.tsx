import { Badge, Button, Checkbox, Flex, Select, Text, TextArea, TextField } from "@radix-ui/themes";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { ApiError } from "@/api/client";
import {
  jobsApi,
  type EncounterInput,
  type IntakeCreate,
  type IntakeSave,
  type JobDetail,
  type JobIntake,
} from "@/api/jobs";
import { DateInput } from "@/components/ui/date-input";
import { JobDetailPanel } from "./job-detail";
import { JobError, JobField, JobMatchBadge } from "./job-fields";
import {
  createComposeDraft,
  DEFAULT_PLATFORM,
  EMPTY_JOB,
  JOB_POLL_INTERVAL,
  JOB_PROFILE_QUERY_KEY,
  jobStatusColor,
  type ComposeDraft,
} from "./job-options";

const otherPlatform = "other";

export function JobEvaluateWorkspace({
  draft,
  setDraft,
  activeIntake,
  evaluatedJobId,
  intakes,
  intakesError,
  onRetryIntakes,
  onSelectIntake,
  onClearIntake,
  onEvaluated,
  onResetEvaluation,
  onUpdateJob,
  onChangeIntakes,
  onDiscardIntake,
  onOpenProfile,
  onOpenLibrary,
}: {
  draft: ComposeDraft;
  setDraft: (updater: (current: ComposeDraft) => ComposeDraft) => void;
  activeIntake: JobIntake | null;
  evaluatedJobId: number | null;
  intakes: JobIntake[] | undefined;
  intakesError: Error | null;
  onRetryIntakes: () => void;
  onSelectIntake: (intake: JobIntake) => void;
  onClearIntake: () => void;
  onEvaluated: (job: JobDetail) => void;
  onResetEvaluation: () => void;
  onUpdateJob: (job: JobDetail) => void;
  onChangeIntakes: () => void;
  onDiscardIntake: (id: number) => void;
  onOpenProfile: () => void;
  onOpenLibrary: (jobId: number) => void;
}) {
  const platformId = useId();
  const profileQuery = useQuery({ queryKey: JOB_PROFILE_QUERY_KEY, queryFn: jobsApi.profile });
  const [revision, setRevision] = useState(0);
  const [phase, setPhase] = useState<"preparing" | "analyzing" | null>(null);
  const [submitted, setSubmitted] = useState<IntakeCreate | null>(null);
  const [handoffError, setHandoffError] = useState<Error | null>(null);

  const actualPlatform =
    draft.platform === otherPlatform ? draft.customPlatform.trim() : draft.platform;
  const greeting = draft.greetingOverride ?? draft.platform === DEFAULT_PLATFORM;
  const missingResume = profileQuery.isSuccess && !profileQuery.data.resume_text.trim();

  const detail = useQuery({
    queryKey: ["jobs", "detail", evaluatedJobId],
    queryFn: () => (evaluatedJobId === null ? null : jobsApi.detail(evaluatedJobId)),
    enabled: evaluatedJobId !== null,
    refetchInterval: ({ state: { data } }) =>
      data?.analysis_status === "pending" ||
      data?.unfinished_questions.some((item) => item.status === "pending")
        ? JOB_POLL_INTERVAL
        : false,
  });

  const evaluate = useMutation({
    mutationFn: async (body: IntakeCreate) => {
      setPhase("preparing");
      const intake = await jobsApi.prepare(body);
      if (intake.status === "saved" && intake.job_id !== null) {
        return { kind: "evaluated" as const, job: await jobsApi.detail(intake.job_id) };
      }
      if (intake.status === "ready" && intake.candidates.length === 0 && intake.fields !== null) {
        setPhase("analyzing");
        try {
          const job = await jobsApi.saveIntake(intake.id, {
            decision: "new_analyze",
            fields: intake.fields,
            encounter: intake.encounter,
          });
          return { kind: "evaluated" as const, job };
        } catch (error) {
          if (error instanceof ApiError && error.status === 422) {
            return {
              kind: "intake" as const,
              intake,
              error: error as Error,
            };
          }
          const refreshed = await jobsApi.intake(intake.id).catch(() => null);
          if (refreshed?.status === "saved" && refreshed.job_id !== null) {
            return { kind: "evaluated" as const, job: await jobsApi.detail(refreshed.job_id) };
          }
          return {
            kind: "intake" as const,
            intake: refreshed ?? intake,
            error: error instanceof Error ? error : new Error("保存并分析失败"),
          };
        }
      }
      return { kind: "intake" as const, intake, error: null };
    },
    onSuccess: (outcome) => {
      setPhase(null);
      setSubmitted(null);
      onChangeIntakes();
      if (outcome.kind === "evaluated") {
        setHandoffError(null);
        setDraft(() => createComposeDraft());
        onEvaluated(outcome.job);
      } else {
        setHandoffError(outcome.error);
        setDraft(() => createComposeDraft());
        onSelectIntake(outcome.intake);
        setRevision((value) => value + 1);
      }
    },
    onError: (error) => {
      setPhase(null);
      if (error instanceof ApiError && [400, 413, 422].includes(error.status)) {
        setSubmitted(null);
      }
      onChangeIntakes();
    },
  });

  const retryPrepare = useMutation({
    mutationFn: (id: number) => jobsApi.retryIntake(id),
    onSuccess: (intake) => {
      setHandoffError(null);
      onSelectIntake(intake);
      setRevision((value) => value + 1);
      onChangeIntakes();
    },
    onError: onChangeIntakes,
  });

  const save = useMutation({
    mutationFn: async ({ id, body }: { id: number; body: IntakeSave }) => {
      try {
        return await jobsApi.saveIntake(id, body);
      } catch (error) {
        if (error instanceof ApiError && error.status === 422) throw error;
        const status = await jobsApi.intake(id).catch(() => null);
        if (status?.status === "saved" && status.job_id !== null) {
          return jobsApi.detail(status.job_id);
        }
        throw error;
      }
    },
    onSuccess: (job) => {
      setHandoffError(null);
      onChangeIntakes();
      onEvaluated(job);
    },
    onError: onChangeIntakes,
  });

  const discard = useMutation({
    mutationFn: jobsApi.discardIntake,
    onSuccess: (_, id) => {
      setHandoffError(null);
      onDiscardIntake(id);
    },
  });

  const busy = evaluate.isPending || retryPrepare.isPending || save.isPending || discard.isPending;
  const activeId = activeIntake?.id;
  const pendingIntake = activeIntake?.status === "pending";
  const progress = useQuery({
    queryKey: ["jobs", "intake", activeId],
    queryFn: () => (activeId === undefined ? null : jobsApi.intake(activeId)),
    enabled: pendingIntake && !busy,
    refetchInterval: ({ state: { data } }) =>
      pendingIntake && !busy && (data?.status ?? "pending") === "pending"
        ? JOB_POLL_INTERVAL
        : false,
  });
  const currentIntake = pendingIntake ? (progress.data ?? activeIntake) : activeIntake;

  return (
    <div className="jobs-fields">
      {intakesError && (
        <Flex align="center" gap="2" wrap="wrap">
          <JobError error={`未能读取待处理的 JD：${intakesError.message}`} />
          <Button size="1" variant="soft" onClick={onRetryIntakes}>
            重试
          </Button>
        </Flex>
      )}

      {!!intakes?.length && (
        <section aria-label="待处理的 JD" className="jobs-pending">
          <Text size="2" weight="medium">
            待处理 JD
          </Text>
          {intakes.map((item) => (
            <Button
              key={item.id}
              size="1"
              variant={currentIntake?.id === item.id ? "solid" : "soft"}
              color={currentIntake?.id === item.id ? undefined : "gray"}
              onClick={() => {
                setHandoffError(null);
                save.reset();
                retryPrepare.reset();
                onSelectIntake(item);
                setRevision((value) => value + 1);
              }}
            >
              {item.fields?.role || `${item.encounter.date} · ${item.encounter.platform}`}
              {item.status === "failed" && (
                <Badge color="amber" size="1">
                  提取失败
                </Badge>
              )}
              {item.candidates.length > 0 && item.status === "ready" && (
                <Badge color="gray" size="1">
                  疑似重复
                </Badge>
              )}
            </Button>
          ))}
        </section>
      )}

      {evaluatedJobId !== null ? (
        <div className="jobs-fields">
          <div className="jobs-eval-result-bar">
            <Text size="2" color="gray">
              {detail.data?.analysis_status === "pending" ? "正在生成匹配分析…" : "评估已完成"}
            </Text>
            <Flex gap="2" wrap="wrap">
              <Button size="2" variant="soft" onClick={() => onOpenLibrary(evaluatedJobId)}>
                在岗位库查看
              </Button>
              <Button size="2" onClick={onResetEvaluation}>
                评估下一份 JD
              </Button>
            </Flex>
          </div>
          {detail.isPending && (
            <p className="loading-message" role="status">
              正在读取评估结果…
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
            <JobDetailPanel key={detail.data.id} job={detail.data} onUpdate={onUpdateJob} />
          )}
        </div>
      ) : currentIntake ? (
        <section className="content-panel jobs-fields" aria-label="确认 JD">
          <Flex justify="between" align="center" gap="2" wrap="wrap">
            <Text size="3" weight="medium">
              {currentIntake.candidates.length ? "检测到可能重复的岗位" : "确认 JD 信息"}
              <Text size="2" color="gray">
                {" "}
                · {currentIntake.encounter.date} · {currentIntake.encounter.platform}
              </Text>
            </Text>
            <Flex gap="2" wrap="wrap">
              <Button
                type="button"
                size="2"
                variant="soft"
                disabled={busy}
                onClick={() => {
                  setHandoffError(null);
                  save.reset();
                  retryPrepare.reset();
                  onClearIntake();
                }}
              >
                返回录入新 JD
              </Button>
              <Button
                type="button"
                size="2"
                color="red"
                variant="soft"
                loading={discard.isPending}
                disabled={busy || currentIntake.status === "saved"}
                onClick={() => {
                  if (window.confirm("丢弃这份待确认的 JD？不会影响已有岗位记录。")) {
                    discard.mutate(currentIntake.id);
                  }
                }}
              >
                丢弃
              </Button>
            </Flex>
          </Flex>
          <JobError error={discard.error} />
          {currentIntake.status === "saved" && currentIntake.job_id !== null ? (
            <Button type="button" onClick={() => onOpenLibrary(currentIntake.job_id!)}>
              在岗位库查看已保存的岗位
            </Button>
          ) : (
            <IntakeReview
              key={`${currentIntake.id}-${currentIntake.status}-${revision}`}
              intake={currentIntake}
              busy={busy}
              retrying={retryPrepare.isPending}
              saving={save.isPending}
              error={save.error ?? retryPrepare.error ?? handoffError}
              onSave={(body) => save.mutate({ id: currentIntake.id, body })}
              onRetry={() => {
                save.reset();
                setHandoffError(null);
                retryPrepare.mutate(currentIntake.id);
              }}
            />
          )}
        </section>
      ) : (
        <section className="content-panel" aria-label="评估 JD">
          <form
            className="jobs-fields"
            onSubmit={(event) => {
              event.preventDefault();
              if (busy || !draft.rawJd.trim() || !actualPlatform) return;
              const body = submitted ?? {
                request_id: crypto.randomUUID(),
                raw_jd: draft.rawJd,
                date: draft.date,
                platform: actualPlatform,
                contact: draft.contact,
                salary: draft.salary,
                notes: draft.notes,
                greeting_enabled: greeting,
              };
              setSubmitted(body);
              evaluate.mutate(body);
            }}
          >
            <fieldset className="jobs-fields" disabled={busy || submitted !== null}>
              <JobField label="JD 原文">
                <TextArea
                  autoFocus
                  required
                  rows={11}
                  placeholder="粘贴完整 JD 原文；若平台薪资显示乱码（如 -K·薪），可在末尾手补如 18-30"
                  value={draft.rawJd}
                  onChange={(event) => {
                    const value = event.target.value;
                    setDraft((current) => ({ ...current, rawJd: value }));
                  }}
                />
              </JobField>
              <div className="jobs-eval-row">
                <div className="jobs-field">
                  <Text as="label" size="2" weight="medium" htmlFor={platformId}>
                    平台
                  </Text>
                  <Select.Root
                    value={draft.platform}
                    onValueChange={(next) =>
                      setDraft((current) => ({
                        ...current,
                        platform: next,
                        greetingOverride: null,
                      }))
                    }
                  >
                    <Select.Trigger id={platformId} />
                    <Select.Content>
                      <Select.Item value={DEFAULT_PLATFORM}>{DEFAULT_PLATFORM}</Select.Item>
                      <Select.Item value="智联招聘">智联招聘</Select.Item>
                      <Select.Item value={otherPlatform}>其他</Select.Item>
                    </Select.Content>
                  </Select.Root>
                </div>
                {draft.platform === otherPlatform && (
                  <JobField label="平台名称">
                    <TextField.Root
                      required
                      placeholder="例如：猎聘"
                      value={draft.customPlatform}
                      onChange={(event) => {
                        const value = event.target.value;
                        setDraft((current) => ({ ...current, customPlatform: value }));
                      }}
                    />
                  </JobField>
                )}
                <label className="jobs-checkbox jobs-eval-greeting">
                  <Checkbox
                    checked={greeting}
                    onCheckedChange={(checked) =>
                      setDraft((current) => ({
                        ...current,
                        greetingOverride: checked === true,
                      }))
                    }
                  />
                  生成开场白
                </label>
              </div>
              <details className="jobs-disclosure">
                <summary>补充日期、联系人或备注</summary>
                <div className="jobs-fields">
                  <div className="jobs-fields-grid">
                    <JobField label="日期">
                      <DateInput
                        required
                        value={draft.date}
                        onChange={(event) => {
                          const value = event.target.value;
                          setDraft((current) => ({ ...current, date: value }));
                        }}
                      />
                    </JobField>
                    <JobField label="联系人">
                      <TextField.Root
                        value={draft.contact}
                        onChange={(event) => {
                          const value = event.target.value;
                          setDraft((current) => ({ ...current, contact: value }));
                        }}
                      />
                    </JobField>
                    <JobField label="薪资">
                      <TextField.Root
                        placeholder="留空则从原文提取"
                        value={draft.salary}
                        onChange={(event) => {
                          const value = event.target.value;
                          setDraft((current) => ({ ...current, salary: value }));
                        }}
                      />
                    </JobField>
                  </div>
                  <JobField label="备注">
                    <TextArea
                      rows={2}
                      value={draft.notes}
                      onChange={(event) => {
                        const value = event.target.value;
                        setDraft((current) => ({ ...current, notes: value }));
                      }}
                    />
                  </JobField>
                </div>
              </details>
            </fieldset>

            {missingResume && (
              <Flex align="center" gap="2" wrap="wrap">
                <Text size="2" color="amber">
                  尚未保存简历正文，请先完善求职资料后再做匹配分析。
                </Text>
                <Button type="button" size="1" variant="soft" onClick={onOpenProfile}>
                  去填写求职资料
                </Button>
              </Flex>
            )}

            <JobError error={evaluate.error} />

            <Flex align="center" justify="between" gap="3" wrap="wrap">
              <Text size="2" color="gray" role="status">
                {phase === "preparing"
                  ? "正在检查重复并提取岗位…"
                  : phase === "analyzing"
                    ? "未发现重复，正在思考并生成匹配分析…"
                    : ""}
              </Text>
              <Flex gap="2" wrap="wrap">
                {submitted && !busy && (
                  <Button
                    type="button"
                    variant="soft"
                    onClick={() => {
                      setSubmitted(null);
                      evaluate.reset();
                    }}
                  >
                    修改原文
                  </Button>
                )}
                <Button
                  type="submit"
                  loading={busy}
                  disabled={!draft.rawJd.trim() || !actualPlatform || missingResume}
                >
                  {submitted ? "重试评估" : "开始评估"}
                </Button>
              </Flex>
            </Flex>
          </form>
        </section>
      )}
    </div>
  );
}

function IntakeReview({
  intake,
  busy,
  retrying,
  saving,
  error,
  onSave,
  onRetry,
}: {
  intake: JobIntake;
  busy: boolean;
  retrying: boolean;
  saving: boolean;
  error: Error | null;
  onSave: (entry: IntakeSave) => void;
  onRetry: () => void;
}) {
  const initialFields = intake.fields ?? EMPTY_JOB;
  const [role, setRole] = useState(initialFields.role);
  const [company, setCompany] = useState(initialFields.company);
  const [city, setCity] = useState(initialFields.city);
  const [salary, setSalary] = useState(intake.encounter.salary || initialFields.salary);
  const [notes, setNotes] = useState(intake.encounter.notes || initialFields.notes);
  const [isHeadhunter, setIsHeadhunter] = useState(initialFields.is_headhunter);
  const [agency, setAgency] = useState(initialFields.headhunter_agency);
  const [encounter, setEncounter] = useState<EncounterInput>(intake.encounter);
  const [showNew, setShowNew] = useState(intake.candidates.length === 0);

  const pending = intake.status === "pending";
  const setEncounterField = <K extends keyof EncounterInput>(key: K, value: EncounterInput[K]) =>
    setEncounter((current) => ({ ...current, [key]: value }));

  return (
    <div className="jobs-fields">
      {intake.error && <JobError error={intake.error} />}
      {(intake.status === "failed" || pending) && (
        <Flex align="center" gap="2" wrap="wrap">
          <Button variant="soft" loading={retrying} disabled={busy} onClick={onRetry}>
            {pending ? "刷新进度或重试" : "重试提取"}
          </Button>
          {!pending && (
            <Text size="2" color="gray">
              也可直接手动补全岗位字段后分析。
            </Text>
          )}
        </Flex>
      )}

      {!!intake.candidates.length && (
        <div className="jobs-fields">
          <Text size="2" weight="medium">
            {intake.match_source === "text" ? "发现高度相似的 JD 原文" : "发现可能相同的历史岗位"}
          </Text>
          {intake.candidates.map((candidate) => (
            <section className="jobs-candidate" key={candidate.id}>
              <Flex gap="2" align="center" wrap="wrap">
                <Text weight="medium">{candidate.role}</Text>
                <Badge color={jobStatusColor(candidate.status)}>{candidate.status}</Badge>
                <JobMatchBadge analysis={candidate.latest_analysis} />
              </Flex>
              <Text as="p" size="2" color="gray">
                {[
                  candidate.company || "实际招聘公司未确认",
                  candidate.city,
                  candidate.salary,
                  `${candidate.encounter_count} 次遇见`,
                  candidate.latest_encounter_date,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </Text>
              {candidate.latest_analysis?.verdict && (
                <Text as="p" size="2">
                  {candidate.latest_analysis.verdict}
                </Text>
              )}
              <Flex wrap="wrap" gap="2">
                <Button
                  size="2"
                  variant="soft"
                  disabled={busy || pending || !encounter.date || !candidate.latest_analysis}
                  onClick={() =>
                    onSave({ decision: "merge_reuse", job_id: candidate.id, encounter })
                  }
                >
                  合并并复用分析
                </Button>
                <Button
                  size="2"
                  variant="outline"
                  disabled={busy || pending || !encounter.date}
                  onClick={() =>
                    onSave({ decision: "merge_analyze", job_id: candidate.id, encounter })
                  }
                >
                  合并并重新分析
                </Button>
              </Flex>
            </section>
          ))}
          {!showNew && (
            <details className="jobs-disclosure">
              <summary>补充这次遇见的记录或查看原文</summary>
              <div className="jobs-fields">
                <fieldset className="jobs-fields" disabled={busy || pending}>
                  <div className="jobs-fields-grid">
                    <JobField label="日期">
                      <DateInput
                        value={encounter.date}
                        onChange={(event) => setEncounterField("date", event.target.value)}
                      />
                    </JobField>
                    <JobField label="联系人">
                      <TextField.Root
                        value={encounter.contact ?? ""}
                        onChange={(event) => setEncounterField("contact", event.target.value)}
                      />
                    </JobField>
                    <JobField label="薪资">
                      <TextField.Root
                        value={encounter.salary ?? ""}
                        onChange={(event) => setEncounterField("salary", event.target.value)}
                      />
                    </JobField>
                  </div>
                  <JobField label="备注">
                    <TextArea
                      rows={2}
                      value={encounter.notes ?? ""}
                      onChange={(event) => setEncounterField("notes", event.target.value)}
                    />
                  </JobField>
                </fieldset>
                <Text as="p" size="2" color="gray">
                  JD 原文
                </Text>
                <div className="jobs-original-jd jobs-prose">{encounter.raw_jd}</div>
              </div>
            </details>
          )}
        </div>
      )}

      <JobError error={error} />
      {saving && (
        <Text size="2" role="status" color="gray">
          正在保存并生成分析…
        </Text>
      )}

      {!pending &&
        (showNew ? (
          <form
            className="jobs-fields"
            onSubmit={(event) => {
              event.preventDefault();
              if (!busy && role.trim() && encounter.date) {
                onSave({
                  decision: "new_analyze",
                  fields: {
                    role,
                    company,
                    city,
                    salary,
                    status: "待决定",
                    notes,
                    is_headhunter: isHeadhunter,
                    headhunter_agency: agency,
                  },
                  encounter: {
                    ...encounter,
                    salary,
                    notes,
                  },
                });
              }
            }}
          >
            {intake.candidates.length > 0 && (
              <Text size="2" weight="medium">
                作为不同岗位新建
              </Text>
            )}
            <fieldset disabled={busy} className="jobs-fields">
              <div className="jobs-fields-grid">
                <JobField label="职位">
                  <TextField.Root
                    required
                    value={role}
                    onChange={(event) => setRole(event.target.value)}
                  />
                </JobField>
                <JobField label="实际招聘公司">
                  <TextField.Root
                    placeholder="猎头未公开时留空"
                    value={company}
                    onChange={(event) => setCompany(event.target.value)}
                  />
                </JobField>
                <JobField label="城市">
                  <TextField.Root value={city} onChange={(event) => setCity(event.target.value)} />
                </JobField>
                <JobField label="薪资">
                  <TextField.Root
                    value={salary}
                    onChange={(event) => setSalary(event.target.value)}
                  />
                </JobField>
                <JobField label="日期">
                  <DateInput
                    required
                    value={encounter.date}
                    onChange={(event) => setEncounterField("date", event.target.value)}
                  />
                </JobField>
                <JobField label="联系人">
                  <TextField.Root
                    value={encounter.contact ?? ""}
                    onChange={(event) => setEncounterField("contact", event.target.value)}
                  />
                </JobField>
              </div>
              <label className="jobs-checkbox">
                <Checkbox
                  checked={isHeadhunter}
                  onCheckedChange={(checked) => setIsHeadhunter(checked === true)}
                />
                由猎头发布
              </label>
              {(isHeadhunter || agency) && (
                <JobField label="猎头机构（不是招聘公司）">
                  <TextField.Root
                    value={agency}
                    onChange={(event) => setAgency(event.target.value)}
                  />
                </JobField>
              )}
              <JobField label="备注">
                <TextArea
                  rows={2}
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                />
              </JobField>
              <details className="jobs-disclosure">
                <summary>查看 JD 原文</summary>
                <div className="jobs-original-jd jobs-prose">{encounter.raw_jd}</div>
              </details>
            </fieldset>
            <Flex justify="end" gap="2" wrap="wrap">
              {intake.candidates.length > 0 && (
                <Button
                  type="button"
                  variant="soft"
                  disabled={busy}
                  onClick={() => setShowNew(false)}
                >
                  返回合并选项
                </Button>
              )}
              <Button
                type="submit"
                loading={saving}
                disabled={busy || !role.trim() || !encounter.date}
              >
                保存并分析
              </Button>
            </Flex>
          </form>
        ) : (
          <Flex justify="end">
            <Button variant="outline" disabled={busy} onClick={() => setShowNew(true)}>
              都不是，作为新岗位新建
            </Button>
          </Flex>
        ))}
    </div>
  );
}
