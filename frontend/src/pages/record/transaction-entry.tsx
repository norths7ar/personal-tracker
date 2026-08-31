import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  api,
  type TransactionCreate,
  type TransactionPreparation,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  Feedback,
  Field,
  selectClass,
  textareaClass,
  today,
} from "@/pages/record/entry-shared";

const types = ["支出", "收入", "迁移"] as const;

const initialEntry: TransactionCreate = {
  type: "支出",
  description: "",
  amount: 0,
  date: today,
  category: null,
  subcategory: null,
  notes: null,
  confidence: null,
  reviewed: false,
};

export function TransactionEntry() {
  const queryClient = useQueryClient();
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: api.categories,
  });
  const [entry, setEntry] = useState<TransactionCreate>(initialEntry);
  const [review, setReview] = useState<TransactionPreparation | null>(null);
  const [requestKey, setRequestKey] = useState("");
  const [pendingSave, setPendingSave] = useState<TransactionCreate | null>(null);
  const [message, setMessage] = useState("");

  const save = useMutation({
    mutationFn: ({ payload, key }: { payload: TransactionCreate; key: string }) =>
      api.createTransaction(payload, key),
    onSuccess: (result) => {
      setMessage(
        result.duplicate
          ? "该请求已经保存，重复提交已忽略。"
          : `已保存账目 #${result.id}`,
      );
      setReview(null);
      setRequestKey("");
      setPendingSave(null);
      setEntry((current) => ({
        ...current,
        description: "",
        amount: 0,
        notes: null,
      }));
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
    },
  });

  const saveEntry = (payload: TransactionCreate, key: string) => {
    setPendingSave(payload);
    save.mutate({ payload, key });
  };

  const prepare = useMutation({
    mutationFn: () => api.prepareTransaction(entry.type, entry.description),
    onSuccess: (result) => {
      const key = crypto.randomUUID();
      setRequestKey(key);
      if (result.status === "confirmed") {
        const payload = {
          ...entry,
          category: result.category,
          subcategory: result.subcategory || null,
          confidence: result.confidence,
          reviewed: false,
        };
        saveEntry(payload, key);
        return;
      }
      setReview(result);
      setEntry((current) => ({
        ...current,
        category: result.category || null,
        subcategory: result.subcategory || null,
        confidence: result.confidence,
        reviewed: true,
      }));
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    setReview(null);
    setPendingSave(null);
    prepare.mutate();
  };

  const categoryMap = categories.data?.[entry.type] ?? {};
  const subcategories = entry.category
    ? (categoryMap[entry.category] ?? [])
    : [];
  const busy = prepare.isPending || save.isPending;

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5">
      <form className="space-y-4" onSubmit={submit}>
        <div className="flex gap-2">
          {types.map((type) => (
            <button
              type="button"
              key={type}
              onClick={() =>
                setEntry({
                  ...entry,
                  type,
                  category: null,
                  subcategory: null,
                })
              }
              className={cn(
                "rounded-md border px-4 py-2 text-sm",
                entry.type === type
                  ? "border-neutral-900 bg-neutral-900 text-white"
                  : "border-neutral-300",
              )}
            >
              {type}
            </button>
          ))}
        </div>
        <Field label="描述">
          <Input
            value={entry.description}
            required
            onChange={(event) =>
              setEntry({ ...entry, description: event.target.value })
            }
            placeholder="例：中午麦当劳"
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="金额">
            <Input
              type="number"
              min="0.01"
              step="0.01"
              required
              value={entry.amount || ""}
              onChange={(event) =>
                setEntry({ ...entry, amount: Number(event.target.value) })
              }
            />
          </Field>
          <Field label="日期">
            <Input
              type="date"
              required
              value={entry.date}
              onChange={(event) =>
                setEntry({ ...entry, date: event.target.value })
              }
            />
          </Field>
        </div>
        <Field label="备注">
          <textarea
            className={textareaClass}
            value={entry.notes ?? ""}
            onChange={(event) =>
              setEntry({ ...entry, notes: event.target.value || null })
            }
          />
        </Field>
        <Button
          disabled={busy || !entry.description.trim() || entry.amount <= 0}
        >
          {prepare.isPending ? "分析中…" : save.isPending ? "保存中…" : "提交"}
        </Button>
      </form>

      {review && (
        <div className="mt-5 space-y-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <div>
            <strong>请确认分类</strong>
            <p className="text-sm text-neutral-600">{review.reasoning}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="主类别">
              <select
                className={selectClass}
                value={entry.category ?? ""}
                onChange={(event) =>
                  setEntry({
                    ...entry,
                    category: event.target.value || null,
                    subcategory: null,
                  })
                }
              >
                <option value="">无</option>
                {Object.keys(categoryMap).map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
            <Field label="子类别">
              <select
                className={selectClass}
                value={entry.subcategory ?? ""}
                onChange={(event) =>
                  setEntry({
                    ...entry,
                    subcategory: event.target.value || null,
                  })
                }
              >
                <option value="">无</option>
                {subcategories.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </Field>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={() => saveEntry(entry, requestKey)}
              disabled={save.isPending}
            >
              确认保存
            </Button>
            <Button variant="outline" onClick={() => setReview(null)}>
              取消
            </Button>
          </div>
        </div>
      )}

      {save.isError && pendingSave && requestKey && !review && (
        <Button
          className="mt-3"
          variant="outline"
          onClick={() => saveEntry(pendingSave, requestKey)}
        >
          使用同一请求重试保存
        </Button>
      )}
      <Feedback message={message} error={prepare.error ?? save.error} />
    </div>
  );
}
