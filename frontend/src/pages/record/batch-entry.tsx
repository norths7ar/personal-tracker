import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, type BatchPreparation, type BatchRecord } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Feedback,
  Field,
  selectClass,
  textareaClass,
  today,
} from "@/pages/record/entry-shared";

type IndexedRecord = { record: BatchRecord; index: number };

export function BatchEntry() {
  const queryClient = useQueryClient();
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: api.categories,
  });
  const [text, setText] = useState("");
  const [defaultDate, setDefaultDate] = useState(today);
  const [records, setRecords] = useState<BatchRecord[]>([]);
  const [diagnostics, setDiagnostics] = useState<
    BatchPreparation["diagnostics"] | null
  >(null);
  const [submissionId, setSubmissionId] = useState("");
  const [message, setMessage] = useState("");

  const prepare = useMutation({
    mutationFn: () => api.prepareBatch(text, defaultDate),
    onSuccess: (result) => {
      setRecords(result.records);
      setDiagnostics(result.diagnostics);
      setSubmissionId(crypto.randomUUID());
      setMessage(
        result.records.length
          ? `解析出 ${result.records.length} 条记录，请确认。`
          : "没有解析出可保存的记录。",
      );
    },
  });
  const save = useMutation({
    mutationFn: () => api.saveBatch(submissionId, records),
    onSuccess: (result) => {
      setMessage(
        result.duplicate
          ? "该批次已经保存，重复提交已忽略。"
          : `已保存 ${result.saved_count} 条记录。`,
      );
      setRecords([]);
      setDiagnostics(null);
      setText("");
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["home-summary"] });
    },
  });

  const update = (index: number, changes: Partial<BatchRecord>) => {
    setRecords((current) =>
      current.map((record, recordIndex) =>
        recordIndex === index ? { ...record, ...changes } : record,
      ),
    );
  };
  const indexed = records.map((record, index) => ({ record, index }));
  const finance = indexed.filter(({ record }) => record.record_type !== "饮食");
  const meals = indexed.filter(({ record }) => record.record_type === "饮食");

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-neutral-200 bg-white p-5">
        <Field label="默认日期">
          <Input
            className="max-w-52"
            type="date"
            value={defaultDate}
            onChange={(event) => setDefaultDate(event.target.value)}
          />
        </Field>
        <Field label="批量描述" className="mt-4">
          <textarea
            className={`${textareaClass} min-h-40`}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="例：【旅游】火车票、打车、吃饭……上层语义会保留到第二阶段。"
          />
        </Field>
        <Button
          className="mt-4"
          onClick={() => prepare.mutate()}
          disabled={prepare.isPending || !text.trim()}
        >
          {prepare.isPending ? "解析中…" : "解析"}
        </Button>
        <Feedback message={message} error={prepare.error ?? save.error} />
        {diagnostics && (
          <details className="mt-4 text-sm text-neutral-600">
            <summary className="cursor-pointer">解析诊断</summary>
            <p className="mt-2">
              {diagnostics.block_count} 个语义块；返回 {diagnostics.raw_count} 条事件；
              保留 {diagnostics.kept_count} 条；过滤 {diagnostics.rejected_records?.length ?? 0} 条。
            </p>
            {diagnostics.reasoning && <p>{diagnostics.reasoning}</p>}
          </details>
        )}
      </div>

      {finance.length > 0 && (
        <FinanceReview
          rows={finance}
          categories={categories.data ?? {}}
          update={update}
        />
      )}
      {meals.length > 0 && <MealReview rows={meals} update={update} />}

      {records.length > 0 && (
        <div className="sticky bottom-4 z-20 flex gap-2 rounded-lg border border-neutral-300 bg-white p-3 shadow-lg">
          <Button
            onClick={() => save.mutate()}
            disabled={save.isPending || !records.some((record) => record.include)}
          >
            {save.isPending ? "保存中…" : "保存所选记录"}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setRecords([]);
              setDiagnostics(null);
              setSubmissionId("");
            }}
          >
            放弃草稿
          </Button>
        </div>
      )}
    </div>
  );
}

function FinanceReview({
  rows,
  categories,
  update,
}: {
  rows: IndexedRecord[];
  categories: Record<string, Record<string, string[]>>;
  update: (index: number, changes: Partial<BatchRecord>) => void;
}) {
  return (
    <ReviewTable title="账目">
      {rows.map(({ record, index }) => {
        const categoryMap = categories[record.record_type] ?? {};
        const subcategories = categoryMap[record.category] ?? [];
        return (
          <tr className="border-t border-neutral-100" key={index}>
            <IncludeCell record={record} index={index} update={update} />
            <td className="p-2">
              <Input
                type="date"
                value={record.date}
                onChange={(event) => update(index, { date: event.target.value })}
              />
            </td>
            <td className="p-2">
              <select
                className={selectClass}
                value={record.record_type}
                onChange={(event) =>
                  update(index, {
                    record_type: event.target.value as BatchRecord["record_type"],
                    category: "",
                    subcategory: "",
                  })
                }
              >
                {(["支出", "收入", "迁移"] as const).map((type) => (
                  <option key={type}>{type}</option>
                ))}
              </select>
            </td>
            <td className="p-2">
              <Input
                value={record.description}
                onChange={(event) =>
                  update(index, { description: event.target.value })
                }
              />
            </td>
            <td className="p-2">
              <Input
                type="number"
                min="0.01"
                step="0.01"
                value={record.amount ?? ""}
                onChange={(event) =>
                  update(index, { amount: Number(event.target.value) })
                }
              />
            </td>
            <td className="p-2">
              <select
                className={selectClass}
                value={record.category}
                onChange={(event) =>
                  update(index, {
                    category: event.target.value,
                    subcategory: "",
                  })
                }
              >
                <option value="">无</option>
                {Object.keys(categoryMap).map((category) => (
                  <option key={category}>{category}</option>
                ))}
              </select>
            </td>
            <td className="p-2">
              <select
                className={selectClass}
                value={record.subcategory}
                onChange={(event) =>
                  update(index, { subcategory: event.target.value })
                }
              >
                <option value="">无</option>
                {subcategories.map((subcategory) => (
                  <option key={subcategory}>{subcategory}</option>
                ))}
              </select>
            </td>
          </tr>
        );
      })}
    </ReviewTable>
  );
}

function MealReview({
  rows,
  update,
}: {
  rows: IndexedRecord[];
  update: (index: number, changes: Partial<BatchRecord>) => void;
}) {
  return (
    <ReviewTable title="饮食">
      {rows.map(({ record, index }) => (
        <tr className="border-t border-neutral-100" key={index}>
          <IncludeCell record={record} index={index} update={update} />
          <td className="space-y-1 p-2">
            <Input
              type="date"
              value={record.date}
              onChange={(event) => update(index, { date: event.target.value })}
            />
            <Input
              type="time"
              value={record.time}
              onChange={(event) => update(index, { time: event.target.value })}
            />
          </td>
          <td className="p-2 text-neutral-500">饮食</td>
          <td className="p-2">
            <Input
              value={record.description}
              onChange={(event) =>
                update(index, { description: event.target.value })
              }
            />
          </td>
          <td className="p-2" colSpan={2}>
            <Input
              value={foodsToText(record.foods ?? [])}
              onChange={(event) =>
                update(index, { foods: textToFoods(event.target.value) })
              }
              placeholder="菜品:份量【食材1、食材2】；…"
            />
          </td>
          <td className="p-2">
            <Input
              value={record.meal_type ?? ""}
              onChange={(event) =>
                update(index, { meal_type: event.target.value })
              }
              placeholder="餐顿标签"
            />
          </td>
        </tr>
      ))}
    </ReviewTable>
  );
}

function ReviewTable({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
      <h2 className="border-b border-neutral-200 px-4 py-3 font-semibold">{title}</h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1000px] text-sm">
          <thead className="bg-neutral-50 text-left text-xs text-neutral-500">
            <tr>
              <th className="p-3">保存</th><th className="p-3">日期 / 时间</th>
              <th className="p-3">类型</th><th className="p-3">描述</th>
              <th className="p-3">金额 / 食物</th><th className="p-3">主类别</th>
              <th className="p-3">子类别 / 餐顿</th>
            </tr>
          </thead>
          <tbody>{children}</tbody>
        </table>
      </div>
    </div>
  );
}

function IncludeCell({ record, index, update }: { record: BatchRecord; index: number; update: (index: number, changes: Partial<BatchRecord>) => void }) {
  return (
    <td className="p-3">
      <Checkbox
        checked={record.include}
        onCheckedChange={(checked) => update(index, { include: Boolean(checked) })}
      />
    </td>
  );
}

function foodsToText(foods: NonNullable<BatchRecord["foods"]>): string {
  return foods
    .map((food) => {
      let value = food.food_name;
      if (food.quantity) value += `:${food.quantity}`;
      if (food.ingredients?.length) value += `【${food.ingredients.join("、")}】`;
      return value;
    })
    .join("；");
}

function textToFoods(value: string): NonNullable<BatchRecord["foods"]> {
  return value
    .split(/[；;]/)
    .map((part) => {
      const ingredientMatch = part.match(/【(.*)】$/);
      const withoutIngredients = ingredientMatch
        ? part.slice(0, ingredientMatch.index)
        : part;
      const [foodName = "", quantity = ""] = withoutIngredients.split(/[:：]/, 2);
      return {
        food_name: foodName.trim(),
        quantity: quantity.trim(),
        ingredients: (ingredientMatch?.[1] ?? "")
          .split(/[、,，]/)
          .map((item) => item.trim())
          .filter(Boolean),
      };
    })
    .filter((food) => food.food_name);
}
