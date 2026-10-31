import { TextArea } from "@radix-ui/themes";

import "@/styles/transaction-entry.css";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, type TransactionCreate, type TransactionPreparation } from "@/api/client";
import { invalidateFinance } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { Feedback, Field, selectClass, textareaClass, today } from "@/pages/record/entry-shared";

const types = ["支出", "收入", "迁移"] as const;

const initialEntry = (): TransactionCreate => ({
  type: "支出",
  description: "",
  amount: 0,
  date: today(),
  category: null,
  subcategory: null,
  notes: null,
  confidence: null,
  reviewed: false,
});

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
      void invalidateFinance(queryClient);
      setMessage(
        result.duplicate ? "该请求已经保存，重复提交已忽略。" : `已保存账目 #${result.id}`,
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
  const subcategories = entry.category ? (categoryMap[entry.category] ?? []) : [];
  const busy = prepare.isPending || save.isPending;

  return (
    <div className="content-panel">
      <form className="form-stack" onSubmit={submit}>
        <div className="entry-actions">
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
                "transaction-type",
                entry.type === type ? "transaction-type-selected" : "transaction-type-idle",
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
            onChange={(event) => setEntry({ ...entry, description: event.target.value })}
            placeholder="例：中午麦当劳"
          />
        </Field>
        <div className="entry-fields">
          <Field label="金额">
            <Input
              type="number"
              min="0.01"
              step="0.01"
              required
              value={entry.amount || ""}
              onChange={(event) => setEntry({ ...entry, amount: Number(event.target.value) })}
            />
          </Field>
          <Field label="日期">
            <Input
              type="date"
              required
              value={entry.date}
              onChange={(event) => setEntry({ ...entry, date: event.target.value })}
            />
          </Field>
        </div>
        <Field label="备注">
          <TextArea
            className={textareaClass}
            value={entry.notes ?? ""}
            onChange={(event) => setEntry({ ...entry, notes: event.target.value || null })}
          />
        </Field>
        <Button
          data-primary-action={!review}
          disabled={busy || !entry.description.trim() || entry.amount <= 0}
        >
          {prepare.isPending ? "分析中…" : save.isPending ? "保存中…" : "提交"}
        </Button>
      </form>

      {review && (
        <div className="entry-review">
          <div>
            <strong>请确认分类</strong>
            <p className="entry-description">{review.reasoning}</p>
          </div>
          <div className="entry-fields">
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
          <div className="entry-actions">
            <Button
              data-primary-action="true"
              onClick={() => saveEntry(entry, requestKey)}
              disabled={busy}
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
          className="entry-primary-action"
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
