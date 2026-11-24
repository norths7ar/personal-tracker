import { TextArea } from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, settingsApi, type TransactionCreate } from "@/api/client";
import { invalidateFinance } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Feedback, Field, selectClass, textareaClass, today } from "./entry-shared";

const initialEntry = () => ({
  type: "支出" as "支出" | "收入" | "迁移",
  description: "",
  amount: "",
  date: today(),
  category: "",
  subcategory: "",
  notes: "",
});
type SaveRequest = { payload: TransactionCreate; key: string };

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
    mutationFn: ({ payload, key }: SaveRequest) => api.createTransaction(payload, key),
    onSuccess: (result) => {
      void invalidateFinance(client);
      setMessage(
        result.duplicate ? "这笔收支已保存。" : "已保存。未确认分类的支出可在待处理中补全。",
      );
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
    };
    const request =
      pending && JSON.stringify(pending.payload) === JSON.stringify(payload)
        ? pending
        : { payload, key: crypto.randomUUID() };
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
          <summary>类型、日期、分类与备注</summary>
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
              <Field label="主类别（可选）">
                <select
                  className={selectClass}
                  value={entry.category}
                  onChange={(event) =>
                    setEntry({ ...entry, category: event.target.value, subcategory: "" })
                  }
                >
                  <option value="">稍后分类</option>
                  {Object.keys(categoryMap).map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </Field>
              {subcategories.length > 0 && (
                <Field label="子类别（可选）">
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
            <Field label="备注（可选）">
              <TextArea
                className={textareaClass}
                value={entry.notes}
                onChange={(event) => setEntry({ ...entry, notes: event.target.value })}
              />
            </Field>
          </div>
        </details>
        <Button
          data-primary-action="true"
          disabled={!entry.description.trim() || Number(entry.amount) <= 0}
        >
          {save.isPending ? "保存中…" : "保存收支"}
        </Button>
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
