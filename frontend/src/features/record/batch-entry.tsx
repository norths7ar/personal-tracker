import { TextArea } from "@radix-ui/themes";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { invalidateCapture } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Feedback, Field, textareaClass } from "./entry-shared";
import {
  beginCaptureSubmission,
  completeCaptureSubmission,
  updateCaptureDraft,
  useCaptureDraft,
} from "./capture-draft";
import { PhraseSuggestions } from "./phrase-suggestions";
import "./batch-entry.css";

export function BatchEntry() {
  const queryClient = useQueryClient();
  const { draft, storageError } = useCaptureDraft();
  const [message, setMessage] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const submit = useMutation({
    mutationFn: () => {
      const pending = beginCaptureSubmission();
      return api
        .submitCapture(pending.text, pending.date, pending.key)
        .then((result) => ({ result, key: pending.key }));
    },
    onSuccess: ({ result, key }) => {
      completeCaptureSubmission(key);
      setMessage(result.duplicate ? "这段记录已收到。" : "已收下，后台整理中。");
      void invalidateCapture(queryClient);
    },
  });
  const append = (phrase: string) => {
    const text = draft.text.trimEnd();
    updateCaptureDraft({
      text: text ? `${text}${/[，。；！？、\n]$/.test(text) ? "" : "，"}${phrase}` : phrase,
    });
    input.current?.focus();
  };
  return (
    <form
      className="content-panel record-composer batch-composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (!submit.isPending && (draft.pending || (draft.text.trim() && draft.date)))
          submit.mutate();
      }}
    >
      <div className="composer-heading">
        <div>
          <h2>今天，想记些什么？</h2>
        </div>
        <Field label="记录日期" className="batch-date">
          <Input
            type="date"
            value={draft.date}
            required={!draft.pending}
            onChange={(event) => updateCaptureDraft({ date: event.target.value })}
          />
        </Field>
      </div>
      <Field label="日常描述" className="batch-description">
        <TextArea
          ref={input}
          className={`${textareaClass} batch-input`}
          value={draft.text}
          onChange={(event) => updateCaptureDraft({ text: event.target.value })}
          placeholder={"午饭花了 32 元，吃了番茄牛腩饭。\n下班买了水果 26 元，晚饭在家煮面。"}
        />
      </Field>
      <PhraseSuggestions onInsert={append} />
      {storageError && (
        <p role="alert" className="feedback-error">
          {storageError}
        </p>
      )}
      {draft.pending && !submit.isPending && (
        <p className="help-text">
          上次提交尚未确认。点击下方按钮安全重试；当前输入的新内容会保留。
        </p>
      )}
      <div className="composer-footer">
        <span className="help-text">Ctrl + Enter</span>
        <Button
          data-primary-action="true"
          disabled={submit.isPending || (!draft.pending && (!draft.text.trim() || !draft.date))}
        >
          {submit.isPending ? "正在收下…" : draft.pending ? "确认上次提交" : "提交记录"}
          <ArrowRight size={16} aria-hidden="true" />
        </Button>
      </div>
      <Feedback message={message} error={submit.error} />
      {message && (
        <Link className="reminder-link" to="/pending">
          查看待处理 <ArrowRight size={14} />
        </Link>
      )}
    </form>
  );
}
