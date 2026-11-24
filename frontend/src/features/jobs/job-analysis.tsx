import { Badge, Button, Flex, Heading, Text } from "@radix-ui/themes";
import { useMutation } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useState } from "react";
import { jobsApi, type JobAnalysis, type JobDetail } from "@/api/jobs";
import { JobCopyButton } from "./job-copy";
import { JobError, JobMatchBadge } from "./job-fields";
import { JobMarkdown } from "./job-markdown";
import { formatJobTime } from "./job-options";

export function JobAnalysisPanel({
  job,
  onUpdate,
}: {
  job: JobDetail;
  onUpdate: (value: JobDetail) => void;
}) {
  const [requestId, setRequestId] = useState<string | null>(null);
  const analysis = useMutation({
    mutationFn: (id: string) => jobsApi.analyze(job.id, { request_id: id }),
    onSuccess: (value) => {
      onUpdate(value);
      setRequestId(null);
    },
  });
  const latest = job.latest_analysis;
  const history = job.analyses.filter((item) => item.id !== latest?.id);
  const actionLabel =
    analysis.isError || job.analysis_status === "failed"
      ? "重试分析"
      : latest
        ? "重新分析"
        : "开始分析";
  return (
    <div className="jobs-fields">
      <Flex align="center" justify="between" wrap="wrap" gap="2">
        <Flex align="center" gap="2" wrap="wrap">
          <Heading as="h3" size="3">
            最新匹配
          </Heading>
          <JobMatchBadge analysis={latest} />
          {job.analysis_stale && <Badge color="amber">分析待更新</Badge>}
        </Flex>
        <Button
          size="2"
          variant="soft"
          loading={analysis.isPending}
          onClick={() => {
            const id = requestId ?? crypto.randomUUID();
            setRequestId(id);
            analysis.mutate(id);
          }}
        >
          <RotateCcw size={14} />
          {analysis.isPending ? "正在分析…" : actionLabel}
        </Button>
      </Flex>
      {job.analysis_stale && (
        <Text as="p" size="2" color="gray">
          求职资料已更新，当前结论来自此前的分析。
        </Text>
      )}
      <JobError
        error={
          analysis.error ??
          (job.analysis_status === "failed" ? job.analysis_error || "分析未成功。" : null)
        }
      />
      {latest ? (
        <AnalysisContent analysis={latest} />
      ) : (
        <Text as="p" size="2" color="gray">
          {job.analysis_status === "pending"
            ? "岗位已保存，分析尚未完成。"
            : "没有可用的分析结果。"}
        </Text>
      )}
      {!!history.length && (
        <div className="jobs-fields jobs-history">
          <Heading as="h3" size="3">
            分析历史
          </Heading>
          {history.map((item) => (
            <details key={item.id} className="jobs-disclosure">
              <summary>
                {formatJobTime(item.created_at)} · 匹配 {item.match_level} · {item.verdict}
              </summary>
              <AnalysisContent analysis={item} />
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

function AnalysisContent({ analysis }: { analysis: JobAnalysis }) {
  const greeting = analysis.greeting;
  return (
    <div className="jobs-fields">
      {analysis.verdict && (
        <Text as="p" weight="medium" className="jobs-prose">
          {analysis.verdict}
        </Text>
      )}
      <Text as="p" size="1" color="gray">
        {formatJobTime(analysis.created_at)}
      </Text>
      <JobMarkdown text={analysis.analysis_markdown} />
      {greeting && (
        <section className="jobs-greeting" aria-label="开场白">
          <Flex align="center" justify="between" wrap="wrap" gap="2">
            <Heading as="h4" size="3">
              开场白
            </Heading>
            <JobCopyButton label="复制开场白" load={() => greeting} />
          </Flex>
          <div className="jobs-prose">{greeting}</div>
        </section>
      )}
    </div>
  );
}
