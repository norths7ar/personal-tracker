import { Button, Flex, Text, TextArea } from "@radix-ui/themes";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { useState } from "react";
import { jobsApi, type JobDetail } from "@/api/jobs";
import { JobError, JobField } from "./job-fields";
import { JobMarkdown } from "./job-markdown";
import { formatJobTime } from "./job-options";

type Question = Parameters<typeof jobsApi.ask>[1];
type Attempt = { request: Question; fromDraft: boolean };

export function JobChat({
  job,
  onUpdate,
}: {
  job: JobDetail;
  onUpdate: (value: JobDetail) => void;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [submitted, setSubmitted] = useState<Question | null>(null);
  const ask = useMutation({
    mutationFn: ({ request }: Attempt) => jobsApi.ask(job.id, request),
    onSuccess: (value, { fromDraft }) => {
      onUpdate(value);
      if (fromDraft) {
        setDraft("");
        setSubmitted(null);
      }
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs", "detail", job.id] });
    },
  });
  const unfinished = job.unfinished_questions.filter(
    (item) => item.request_id !== submitted?.request_id,
  );

  return (
    <div className="jobs-fields">
      {job.messages.length ? (
        <ol aria-label="岗位对话" className="jobs-chat-list">
          {job.messages.map((message) => (
            <li key={message.id} className={`jobs-chat-message jobs-chat-${message.role}`}>
              <Flex gap="2" align="baseline" wrap="wrap">
                <Text size="2" weight="medium">
                  {message.role === "user" ? "我" : "AI"}
                </Text>
                <Text size="1" color="gray">
                  {formatJobTime(message.created_at)}
                </Text>
              </Flex>
              {message.role === "assistant" ? (
                <JobMarkdown text={message.content} />
              ) : (
                <div className="jobs-prose">{message.content}</div>
              )}
            </li>
          ))}
        </ol>
      ) : !unfinished.length ? (
        <Text as="p" size="2" color="gray">
          还没有追问。
        </Text>
      ) : null}
      {unfinished.map(({ request_id, question, status, error }) => (
        <div className="jobs-chat-message jobs-chat-user jobs-fields" key={request_id}>
          <Text size="2" weight="medium">
            {status === "pending" ? "尚未收到回复" : "发送未完成"}
          </Text>
          <div className="jobs-prose">{question}</div>
          <JobError
            error={ask.variables?.request.request_id === request_id ? (ask.error ?? error) : error}
          />
          <Flex justify="end">
            <Button
              size="2"
              variant="soft"
              disabled={ask.isPending}
              loading={ask.isPending && ask.variables.request.request_id === request_id}
              onClick={() => ask.mutate({ request: { request_id, question }, fromDraft: false })}
            >
              重试发送
            </Button>
          </Flex>
        </div>
      ))}
      <form
        className="jobs-fields"
        onSubmit={(event) => {
          event.preventDefault();
          if (ask.isPending || !draft.trim()) return;
          const question = submitted ?? { request_id: crypto.randomUUID(), question: draft.trim() };
          setSubmitted(question);
          ask.mutate({ request: question, fromDraft: true });
        }}
      >
        <JobField label="关于这个岗位的问题">
          <TextArea
            rows={3}
            maxLength={10000}
            value={draft}
            disabled={submitted !== null}
            onChange={(event) => setDraft(event.target.value)}
          />
        </JobField>
        {ask.variables?.fromDraft && <JobError error={ask.error} />}
        <Flex gap="2" justify="end" wrap="wrap">
          {submitted && !ask.isPending && (
            <Button
              type="button"
              variant="soft"
              onClick={() => {
                setSubmitted(null);
                ask.reset();
              }}
            >
              编辑问题
            </Button>
          )}
          <Button
            type="submit"
            loading={ask.isPending && ask.variables.fromDraft}
            disabled={ask.isPending || !draft.trim()}
          >
            <Send size={14} />{" "}
            {ask.isPending && ask.variables.fromDraft
              ? "等待回复…"
              : submitted
                ? "重试发送"
                : "发送"}
          </Button>
        </Flex>
      </form>
    </div>
  );
}
