import { Badge, Button, Flex, Heading, Tabs, Text } from "@radix-ui/themes";
import { useMutation } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useState } from "react";
import { jobsApi, type JobDetail, type JobFields } from "@/api/jobs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { JobAnalysisPanel } from "./job-analysis";
import { JobChat } from "./job-chat";
import { JobCopyButton } from "./job-copy";
import { JobError, JobFieldsEditor } from "./job-fields";
import { editableJob } from "./job-options";

export function JobDetailPanel({
  job,
  onUpdate,
}: {
  job: JobDetail;
  onUpdate: (value: JobDetail) => void;
}) {
  const [draft, setDraft] = useState<JobFields | null>(null);
  const update = useMutation({
    mutationFn: (value: JobFields) => jobsApi.update(job.id, value),
    onSuccess: (value) => {
      onUpdate(value);
      setDraft(null);
    },
  });
  return (
    <section className="jobs-detail" aria-labelledby="jobs-detail-heading">
      <header className="jobs-detail-header">
        <div>
          <Flex align="center" gap="2" wrap="wrap">
            <Heading as="h2" size="5" id="jobs-detail-heading">
              {job.role}
            </Heading>
            <Badge color="gray">{job.status}</Badge>
            {job.is_headhunter && <Badge color="gray">猎头</Badge>}
          </Flex>
          <Text as="p" color="gray" size="2">
            {[job.company || "实际招聘公司未确认", job.city, job.salary]
              .filter(Boolean)
              .join(" · ")}
          </Text>
          {job.headhunter_agency && (
            <Text as="p" size="2" color="gray">
              猎头机构：{job.headhunter_agency}
            </Text>
          )}
        </div>
        <Flex gap="2" wrap="wrap">
          <Button
            size="2"
            variant="outline"
            onClick={() => {
              update.reset();
              setDraft(editableJob(job));
            }}
          >
            <Pencil size={14} /> 编辑岗位
          </Button>
          <JobCopyButton
            label="复制完整上下文"
            load={async () => (await jobsApi.context(job.id)).text}
          />
        </Flex>
      </header>
      <Tabs.Root defaultValue="analysis">
        <Tabs.List aria-label="岗位详情">
          <Tabs.Trigger value="analysis">匹配分析</Tabs.Trigger>
          <Tabs.Trigger value="overview">岗位与遇见</Tabs.Trigger>
          <Tabs.Trigger value="chat">继续追问</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="analysis" forceMount className="jobs-tab">
          <JobAnalysisPanel job={job} onUpdate={onUpdate} />
        </Tabs.Content>
        <Tabs.Content value="overview" className="jobs-tab">
          <JobOverview job={job} />
        </Tabs.Content>
        <Tabs.Content value="chat" forceMount className="jobs-tab">
          <JobChat job={job} onUpdate={onUpdate} />
        </Tabs.Content>
      </Tabs.Root>
      <Dialog
        open={draft !== null}
        onOpenChange={(next) => {
          if (!next && !update.isPending) setDraft(null);
        }}
      >
        <DialogContent layout="center" className="jobs-dialog">
          <DialogHeader>
            <DialogTitle>编辑岗位</DialogTitle>
            <DialogDescription>岗位资料的修改不会覆盖已保存的 JD 原文。</DialogDescription>
          </DialogHeader>
          {draft && (
            <form
              className="jobs-fields"
              onSubmit={(event) => {
                event.preventDefault();
                if (draft.role.trim() && !update.isPending) update.mutate(draft);
              }}
            >
              <fieldset disabled={update.isPending}>
                <JobFieldsEditor value={draft} onChange={setDraft} />
              </fieldset>
              <JobError error={update.error} />
              <Flex gap="2" justify="end">
                <Button
                  type="button"
                  variant="soft"
                  onClick={() => setDraft(null)}
                  disabled={update.isPending}
                >
                  关闭
                </Button>
                <Button type="submit" loading={update.isPending} disabled={!draft.role.trim()}>
                  保存岗位
                </Button>
              </Flex>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function JobOverview({ job }: { job: JobDetail }) {
  return (
    <div className="jobs-fields">
      {job.notes && (
        <section>
          <Heading as="h3" size="3">
            岗位备注
          </Heading>
          <div className="jobs-prose">{job.notes}</div>
        </section>
      )}
      <Heading as="h3" size="3">
        遇见记录{" "}
        <Text color="gray" size="2">
          {job.encounter_count} 次
        </Text>
      </Heading>
      {job.encounters.map((encounter, index) => (
        <details key={encounter.id} open={index === 0} className="jobs-disclosure">
          <summary>
            {[encounter.date, encounter.platform, encounter.contact, encounter.salary]
              .filter(Boolean)
              .join(" · ")}
          </summary>
          {encounter.notes && (
            <div className="jobs-prose">
              <Text weight="medium">备注：</Text>
              {encounter.notes}
            </div>
          )}
          <Text as="p" size="2" color="gray">
            JD 原文
          </Text>
          <div className="jobs-original-jd jobs-prose">{encounter.raw_jd}</div>
        </details>
      ))}
    </div>
  );
}
