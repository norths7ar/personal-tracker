import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Clock3, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { api, type CaptureItem } from "@/api/client";
import { invalidateCapture } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { Feedback } from "@/features/record/entry-shared";
import { CaptureEditor } from "./capture-editor";

export function CaptureRow({ item }: { item: CaptureItem }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const busy = item.status === "queued" || item.status === "processing";
  const action = useMutation({
    mutationFn: async (operation: "retry" | "discard") => {
      if (operation === "retry") await api.retryCapture(item.id);
      else await api.discardCapture(item.id);
    },
    onSuccess: () => {
      void invalidateCapture(client);
    },
  });
  const status =
    item.status === "queued"
      ? "等待解析"
      : item.status === "processing"
        ? "解析中"
        : item.status === "failed"
          ? "解析失败"
          : "待确认";
  return (
    <article className={`capture-row ${busy ? "capture-row-working" : "capture-row-review"}`}>
      <button
        type="button"
        className="capture-row-summary"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {busy ? <Clock3 size={16} /> : <AlertCircle size={16} />}
        <span className="capture-row-main">
          <strong>{item.record?.description || item.source_text}</strong>
          <span>{item.reason || (busy ? "原文已保存，可以离开页面。" : "展开补全并确认入账")}</span>
        </span>
        <span className="capture-row-date">{item.record?.date || item.default_date}</span>
        <span className="capture-row-status">{status}</span>
      </button>
      {open && (
        <div className="capture-row-details">
          <details className="capture-source">
            <summary>查看原文</summary>
            <p>{item.original_text}</p>
          </details>
          {!busy && <CaptureEditor item={item} />}
          <div className="entry-actions">
            {item.can_retry && (
              <Button
                type="button"
                variant="outline"
                disabled={action.isPending}
                onClick={() => action.mutate("retry")}
              >
                <RotateCcw size={14} />
                重新解析此项
              </Button>
            )}
            {!busy && (
              <Button
                type="button"
                variant="ghost"
                disabled={action.isPending}
                onClick={() => {
                  if (window.confirm("丢弃这项未入账内容？已入账的记录不会受影响。"))
                    action.mutate("discard");
                }}
              >
                <Trash2 size={14} />
                丢弃
              </Button>
            )}
          </div>
          <Feedback error={action.error} />
        </div>
      )}
    </article>
  );
}
