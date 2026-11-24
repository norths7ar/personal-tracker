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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { JobError, JobField, JobFieldsEditor, JobMatchBadge } from "./job-fields";
import { EMPTY_JOB, JOB_POLL_INTERVAL } from "./job-options";

const defaultPlatform = "BOSS直聘";
const otherPlatform = "other";
const today = () => new Intl.DateTimeFormat("en-CA").format(new Date());

export function JobIntakeDialog({
  open,
  seed,
  onClose,
  onChange,
  onDiscard,
  onSave,
}: {
  open: boolean;
  seed: JobIntake | null;
  onClose: () => void;
  onChange: () => void;
  onDiscard: (id: number) => void;
  onSave: (job: JobDetail) => void;
}) {
  const platformId = useId();
  const [intake, setIntake] = useState(seed);
  const [revision, setRevision] = useState(0);
  const [rawJd, setRawJd] = useState("");
  const [date, setDate] = useState(today);
  const [platform, setPlatform] = useState(defaultPlatform);
  const [customPlatform, setCustomPlatform] = useState("");
  const [contact, setContact] = useState("");
  const [salary, setSalary] = useState("");
  const [notes, setNotes] = useState("");
  const [greetingOverride, setGreetingOverride] = useState<boolean | null>(null);
  const [submitted, setSubmitted] = useState<IntakeCreate | null>(null);
  const actualPlatform = platform === otherPlatform ? customPlatform.trim() : platform;
  const greeting = greetingOverride ?? platform === defaultPlatform;

  function clearDraft() {
    setIntake(null);
    setSubmitted(null);
    setRawJd("");
    setDate(today());
    setContact("");
    setSalary("");
    setNotes("");
    setGreetingOverride(null);
  }

  function saved(job: JobDetail) {
    clearDraft();
    onChange();
    onSave(job);
  }

  const prepare = useMutation({
    mutationFn: async (action: () => Promise<JobIntake>) => {
      const data = await action();
      const job =
        data.status === "saved" && data.job_id !== null ? await jobsApi.detail(data.job_id) : null;
      return { data, job };
    },
    onSuccess: ({ data, job }) => {
      if (job) saved(job);
      else {
        setSubmitted(null);
        setIntake(data);
        setRevision((value) => value + 1);
        onChange();
      }
    },
    onError: (error) => {
      if (error instanceof ApiError && [400, 404, 409, 413, 422].includes(error.status)) {
        setSubmitted(null);
      }
      onChange();
    },
  });
  const save = useMutation({
    mutationFn: async (body: IntakeSave) => {
      if (intake === null) throw new Error("请先录入 JD。");
      try {
        return await jobsApi.saveIntake(intake.id, body);
      } catch (error) {
        if (error instanceof ApiError && error.status === 422) throw error;
        const status = await jobsApi.intake(intake.id).catch(() => null);
        if (status?.status === "saved" && status.job_id !== null) {
          return jobsApi.detail(status.job_id);
        }
        throw error;
      }
    },
    onSuccess: saved,
    onError: onChange,
  });
  const discard = useMutation({
    mutationFn: jobsApi.discardIntake,
    onSuccess: (_value, id) => {
      clearDraft();
      prepare.reset();
      save.reset();
      onDiscard(id);
      onClose();
    },
    onError: onChange,
  });
  const busy = prepare.isPending || save.isPending || discard.isPending;
  const error = save.error ?? prepare.error;
  const intakeId = intake?.id;
  const pending = intake?.status === "pending";
  const progress = useQuery({
    queryKey: ["jobs", "intake", intakeId],
    queryFn: () => (intakeId === undefined ? null : jobsApi.intake(intakeId)),
    enabled: open && pending && !busy,
    refetchInterval: ({ state: { data } }) =>
      open && pending && !busy && (data?.status ?? "pending") === "pending"
        ? JOB_POLL_INTERVAL
        : false,
  });
  const current = pending ? (progress.data ?? intake) : intake;

  function close() {
    if (busy) return;
    // A prepared intake already lives on the server and can be resumed from the pending list.
    if (intake && !seed) {
      clearDraft();
      prepare.reset();
      save.reset();
      discard.reset();
    }
    onClose();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <DialogContent layout="center" className="jobs-dialog">
        <DialogHeader>
          <DialogTitle>{current ? "确认 JD" : "录入 JD"}</DialogTitle>
          <DialogDescription>
            {current
              ? `${current.encounter.date} · ${current.encounter.platform}`
              : "粘贴招聘原文，先检查是否遇见过同一岗位。"}
          </DialogDescription>
        </DialogHeader>
        {current?.status === "saved" ? (
          <div className="jobs-fields">
            <JobError error={error} />
            <Button
              type="button"
              loading={busy}
              onClick={() => prepare.mutate(() => jobsApi.intake(current.id))}
            >
              打开已保存的岗位
            </Button>
          </div>
        ) : current ? (
          <div className="jobs-fields">
            <IntakeReview
              key={`${current.id}-${current.status}-${revision}`}
              intake={current}
              busy={busy}
              preparing={prepare.isPending}
              saving={save.isPending}
              error={error}
              onSave={(body) => save.mutate(body)}
              onRetry={() => {
                save.reset();
                prepare.mutate(() => jobsApi.retryIntake(current.id));
              }}
            />
            <div className="jobs-discard">
              <JobError error={discard.error} />
              <Button
                type="button"
                size="2"
                color="red"
                variant="soft"
                loading={discard.isPending}
                disabled={busy}
                onClick={() => {
                  if (window.confirm("丢弃这份待确认的 JD？此操作不会影响已保存的岗位和遇见。")) {
                    discard.mutate(current.id);
                  }
                }}
              >
                丢弃这份 JD
              </Button>
            </div>
          </div>
        ) : (
          <form
            className="jobs-fields"
            onSubmit={(event) => {
              event.preventDefault();
              if (busy || !rawJd.trim() || !actualPlatform) return;
              const body = submitted ?? {
                request_id: crypto.randomUUID(),
                raw_jd: rawJd,
                date,
                platform: actualPlatform,
                contact,
                salary,
                notes,
                greeting_enabled: greeting,
              };
              setSubmitted(body);
              prepare.mutate(() => jobsApi.prepare(body));
            }}
          >
            <fieldset className="jobs-fields" disabled={busy || submitted !== null}>
              <JobField label="JD 原文">
                <TextArea
                  autoFocus
                  required
                  rows={9}
                  value={rawJd}
                  onChange={(event) => setRawJd(event.target.value)}
                />
              </JobField>
              <div className="jobs-fields-grid">
                <JobField label="遇见日期">
                  <DateInput
                    required
                    value={date}
                    onChange={(event) => setDate(event.target.value)}
                  />
                </JobField>
                <div className="jobs-field">
                  <Text as="label" size="2" weight="medium" htmlFor={platformId}>
                    平台
                  </Text>
                  <Select.Root
                    value={platform}
                    onValueChange={(next) => {
                      setPlatform(next);
                      setGreetingOverride(null);
                    }}
                  >
                    <Select.Trigger id={platformId} />
                    <Select.Content>
                      <Select.Item value={defaultPlatform}>{defaultPlatform}</Select.Item>
                      <Select.Item value="智联招聘">智联招聘</Select.Item>
                      <Select.Item value={otherPlatform}>其他</Select.Item>
                    </Select.Content>
                  </Select.Root>
                </div>
              </div>
              {platform === otherPlatform && (
                <JobField label="平台名称">
                  <TextField.Root
                    required
                    value={customPlatform}
                    onChange={(event) => setCustomPlatform(event.target.value)}
                  />
                </JobField>
              )}
              <label className="jobs-checkbox">
                <Checkbox
                  checked={greeting}
                  onCheckedChange={(checked) => setGreetingOverride(checked === true)}
                />
                生成开场白
              </label>
              <details className="jobs-disclosure">
                <summary>联系人、薪资及备注（可选）</summary>
                <div className="jobs-fields">
                  <div className="jobs-fields-grid">
                    <JobField label="这次遇见的联系人">
                      <TextField.Root
                        value={contact}
                        onChange={(event) => setContact(event.target.value)}
                      />
                    </JobField>
                    <JobField label="这次遇见的薪资">
                      <TextField.Root
                        value={salary}
                        onChange={(event) => setSalary(event.target.value)}
                      />
                    </JobField>
                  </div>
                  <JobField label="这次遇见的备注">
                    <TextArea
                      rows={2}
                      value={notes}
                      onChange={(event) => setNotes(event.target.value)}
                    />
                  </JobField>
                </div>
              </details>
            </fieldset>
            <JobError error={error} />
            <Flex gap="2" wrap="wrap" justify="end">
              <Button type="button" variant="soft" disabled={busy} onClick={close}>
                稍后继续
              </Button>
              <Button type="submit" loading={busy} disabled={!rawJd.trim() || !actualPlatform}>
                {prepare.isPending
                  ? "正在查找重复并提取…"
                  : submitted
                    ? "重试录入"
                    : "检查重复并提取"}
              </Button>
            </Flex>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function IntakeReview({
  intake,
  busy,
  preparing,
  saving,
  error,
  onSave,
  onRetry,
}: {
  intake: JobIntake;
  busy: boolean;
  preparing: boolean;
  saving: boolean;
  error: Error | null;
  onSave: (entry: IntakeSave) => void;
  onRetry: () => void;
}) {
  const [fields, setFields] = useState(intake.fields ?? EMPTY_JOB);
  const [encounter, setEncounter] = useState(intake.encounter);
  const [showNew, setShowNew] = useState(intake.candidates.length === 0);
  const pending = intake.status === "pending";
  const setEncounterField = <K extends keyof EncounterInput>(key: K, value: EncounterInput[K]) =>
    setEncounter((current) => ({ ...current, [key]: value }));

  return (
    <div className="jobs-fields">
      {intake.error && <JobError error={intake.error} />}
      {(intake.status === "failed" || pending) && (
        <Flex align="center" gap="2" wrap="wrap">
          <Button variant="soft" loading={preparing} disabled={busy} onClick={onRetry}>
            {pending ? "查看进度或重试" : "重试提取"}
          </Button>
          {!pending && (
            <Text size="2" color="gray">
              也可以手动填写岗位后保存。
            </Text>
          )}
        </Flex>
      )}
      <details className="jobs-disclosure">
        <summary>查看这次遇见 · {intake.encounter.platform}</summary>
        <Text as="p" size="2" color="gray">
          {intake.greeting_enabled ? "将生成开场白" : "不生成开场白"}
        </Text>
        <fieldset className="jobs-fields" disabled={busy || pending}>
          <div className="jobs-fields-grid">
            <JobField label="遇见日期">
              <TextField.Root
                type="date"
                value={encounter.date}
                onChange={(event) => setEncounterField("date", event.target.value)}
              />
            </JobField>
            <JobField label="这次遇见的联系人">
              <TextField.Root
                value={encounter.contact ?? ""}
                onChange={(event) => setEncounterField("contact", event.target.value)}
              />
            </JobField>
            <JobField label="这次遇见的薪资">
              <TextField.Root
                value={encounter.salary ?? ""}
                onChange={(event) => setEncounterField("salary", event.target.value)}
              />
            </JobField>
          </div>
          <JobField label="这次遇见的备注">
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
      </details>
      {!!intake.candidates.length && (
        <div className="jobs-fields">
          <Text size="2" weight="medium">
            {intake.match_source === "text" ? "发现相同或相近的原文" : "发现可能相同的岗位"}
          </Text>
          {intake.candidates.map((candidate) => (
            <section className="jobs-candidate" key={candidate.id}>
              <Flex gap="2" align="center" wrap="wrap">
                <Text weight="medium">{candidate.role}</Text>
                <Badge color="gray">{candidate.status}</Badge>
                <JobMatchBadge analysis={candidate.latest_analysis} />
              </Flex>
              <Text as="p" size="2" color="gray">
                {[
                  candidate.company || "公司未确认",
                  candidate.city,
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
        </div>
      )}
      <JobError error={error} />
      {saving && (
        <Text size="2" role="status" color="gray">
          正在保存岗位，分析可能需要一些时间…
        </Text>
      )}
      {!pending &&
        (showNew ? (
          <form
            className="jobs-fields"
            onSubmit={(event) => {
              event.preventDefault();
              if (!busy && fields.role.trim() && encounter.date) {
                onSave({ decision: "new_analyze", fields, encounter });
              }
            }}
          >
            <Text size="2" weight="medium">
              {intake.candidates.length ? "作为不同的岗位新建" : "确认岗位资料"}
            </Text>
            <fieldset disabled={busy}>
              <JobFieldsEditor value={fields} onChange={setFields} />
            </fieldset>
            <Flex justify="end">
              <Button
                type="submit"
                loading={saving}
                disabled={busy || !fields.role.trim() || !encounter.date}
              >
                新建并分析
              </Button>
            </Flex>
          </form>
        ) : (
          <Flex justify="end">
            <Button variant="outline" disabled={busy} onClick={() => setShowNew(true)}>
              新建岗位
            </Button>
          </Flex>
        ))}
    </div>
  );
}
