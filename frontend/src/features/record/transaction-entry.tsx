import { TextArea } from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, settingsApi, type TransactionCreate } from "@/api/client";
import { invalidateFinance } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CoverageFields } from "@/features/ledger/coverage-fields";
import { Feedback, Field, selectClass, textareaClass, today } from "./entry-shared";

const initialEntry = () => ({
  type: "支出" as "支出" | "收入" | "迁移",
  description: "",
  amount: "",
  date: today(),
  category: "",
  subcategory: "",
  notes: "",
  coverageStart: "",
  coverageEnd: "",
});
type SaveRequest = {
  signature: string;
  payload: TransactionCreate;
  key: string;
  autoClassify: boolean;
};

export function TransactionEntry() {
  const client = useQueryClient();
  const categories = useQuery({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
    select: (settings) => settings.records.categories,
  });
  const [entry, setEntry] = useState(initialEntry);
  const [pending, setPending] = useState<SaveRequest | null>(null);
  const [message, setMessage] = useState("");
  const save = useMutation({
    mutationFn: async (request: SaveRequest) => {
      let finalPayload = request.payload;
      if (request.autoClassify) {
        try {
          const prep = await api.prepareTransaction(
            request.payload.type,
            request.payload.description,
          );
          finalPayload =
            prep.status === "confirmed"
              ? {
                  ...request.payload,
                  category: prep.category,
                  subcategory: prep.subcategory || null,
                  confidence: prep.confidence ?? null,
                  reviewed: false,
                }
              : {
                  ...request.payload,
                  category: null,
                  subcategory: null,
                  confidence: prep.confidence ?? null,
                  reviewed: false,
                };
        } catch {
          finalPayload = {
            ...request.payload,
            category: null,
            subcategory: null,
            confidence: null,
            reviewed: false,
          };
        }
        setPending({
          signature: request.signature,
          payload: finalPayload,
          key: request.key,
          autoClassify: false,
        });
      }
      const result = await api.createTransaction(finalPayload, request.key);
      return { result, payload: finalPayload };
    },
    onSuccess: ({ result, payload }) => {
      void invalidateFinance(client);
      if (result.duplicate) {
        setMessage("这笔收支已保存。");
      } else if (payload.category) {
        setMessage(
          `已保存（${payload.category}${payload.subcategory ? ` / ${payload.subcategory}` : ""}）。`,
        );
      } else if (payload.type === "支出") {
        setMessage("已保存，可在待处理中确认分类。");
      } else {
        setMessage("已保存。");
      }
      setPending(null);
      setEntry(initialEntry());
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (save.isPending) return;
    const payload: TransactionCreate = {
      type: entry.type,
      description: entry.description.trim(),
      amount: Number(entry.amount),
      date: entry.date || today(),
      category: entry.category || null,
      subcategory: entry.subcategory || null,
      notes: entry.notes.trim() || null,
      reviewed: Boolean(entry.category),
      coverage_start: entry.type === "支出" ? entry.coverageStart || null : null,
      coverage_end: entry.type === "支出" ? entry.coverageEnd || null : null,
    };
    const signature = JSON.stringify(payload);
    const request: SaveRequest =
      pending && pending.signature === signature
        ? pending
        : {
            signature,
            payload,
            key: crypto.randomUUID(),
            autoClassify: payload.type === "支出" && !payload.category,
          };
    setPending(request);
    setMessage("");
    save.mutate(request);
  };
  const categoryMap = categories.data?.[entry.type] ?? {};
  const subcategories = categoryMap[entry.category] ?? [];
  return (
    <form className="content-panel record-composer form-stack" onSubmit={submit}>
      <fieldset disabled={save.isPending} className="form-stack manual-fields">
        <div className="paired-fields">
          <Field label="金额">
            <Input
              type="number"
              min="0.01"
              step="0.01"
              required
              value={entry.amount}
              onChange={(event) => setEntry({ ...entry, amount: event.target.value })}
            />
          </Field>
          <Field label="描述">
            <Input
              required
              value={entry.description}
              placeholder="例：中午麦当劳"
              onChange={(event) => setEntry({ ...entry, description: event.target.value })}
            />
          </Field>
        </div>
        <details className="manual-options">
          <summary>类型、日期、分类、备注与生效期</summary>
          <div className="form-stack">
            <div className="paired-fields">
              <Field label="类型">
                <select
                  className={selectClass}
                  value={entry.type}
                  onChange={(event) =>
                    setEntry({
                      ...entry,
                      type: event.target.value as typeof entry.type,
                      category: "",
                      subcategory: "",
                    })
                  }
                >
                  {["支出", "收入", "迁移"].map((type) => (
                    <option key={type}>{type}</option>
                  ))}
                </select>
              </Field>
              <Field label="日期">
                <Input
                  type="date"
                  value={entry.date}
                  onChange={(event) => setEntry({ ...entry, date: event.target.value })}
                />
              </Field>
            </div>
            <div className="paired-fields">
              <Field label="主类别">
                <select
                  className={selectClass}
                  value={entry.category}
                  onChange={(event) =>
                    setEntry({ ...entry, category: event.target.value, subcategory: "" })
                  }
                >
                  <option value="">{entry.type === "支出" ? "自动分类" : "不选分类"}</option>
                  {Object.keys(categoryMap).map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </Field>
              {subcategories.length > 0 && (
                <Field label="子类别">
                  <select
                    className={selectClass}
                    value={entry.subcategory}
                    onChange={(event) => setEntry({ ...entry, subcategory: event.target.value })}
                  >
                    <option value="">暂不填写</option>
                    {subcategories.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                </Field>
              )}
            </div>
            <Field label="备注">
              <TextArea
                className={textareaClass}
                value={entry.notes}
                onChange={(event) => setEntry({ ...entry, notes: event.target.value })}
              />
            </Field>
            {entry.type === "支出" && (
              <CoverageFields
                start={entry.coverageStart}
                end={entry.coverageEnd}
                paymentDate={entry.date || today()}
                onChange={(coverageStart, coverageEnd) =>
                  setEntry({ ...entry, coverageStart, coverageEnd })
                }
              />
            )}
          </div>
        </details>
        <div className="composer-footer">
          <Button
            data-primary-action="true"
            disabled={save.isPending || !entry.description.trim() || Number(entry.amount) <= 0}
          >
            {save.isPending ? "保存中…" : "保存收支"}
          </Button>
        </div>
      </fieldset>
      {save.isError && pending && (
        <Button type="button" variant="outline" onClick={() => save.mutate(pending)}>
          重试上次保存
        </Button>
      )}
      <Feedback message={message} error={save.error} />
    </form>
  );
}
