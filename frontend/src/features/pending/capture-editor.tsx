import { TextArea } from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, settingsApi, type BatchRecord, type CaptureItem } from "@/api/client";
import { invalidateCapture } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FoodFields } from "@/features/diet/food-fields";
import { MealTypeInput } from "@/features/diet/meal-type-input";
import { Feedback, Field, selectClass, textareaClass } from "@/features/record/entry-shared";

export function CaptureEditor({ item }: { item: CaptureItem }) {
  const client = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: settingsApi.get });
  const [record, setRecord] = useState<BatchRecord>(
    () =>
      item.record ?? {
        include: true,
        confidence: 0,
        reasoning: "",
        record_type: "支出",
        date: item.default_date,
        description: item.source_text,
        amount: null,
        category: "",
        subcategory: "",
        time: "",
        meal_type: "",
        foods: [],
        notes: null,
      },
  );
  const save = useMutation({
    mutationFn: () =>
      api.confirmCapture(item.id, {
        ...record,
        description: record.description.trim(),
        foods: (record.foods ?? []).filter((food) => food.food_name.trim()),
      }),
    onSuccess: () => {
      void invalidateCapture(client);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!save.isPending) save.mutate();
  };
  const meal = record.record_type === "饮食";
  const categoryMap = settings.data?.records.categories[record.record_type] ?? {};
  const subcategories = categoryMap[record.category ?? ""] ?? [];
  return (
    <form className="capture-editor form-stack" onSubmit={submit}>
      <fieldset disabled={save.isPending} className="form-stack capture-fields">
        <div className="paired-fields">
          <Field label="记录类型">
            <select
              className={selectClass}
              value={record.record_type}
              onChange={(event) =>
                setRecord({
                  ...record,
                  record_type: event.target.value as BatchRecord["record_type"],
                  category: "",
                  subcategory: "",
                })
              }
            >
              {["支出", "收入", "迁移", "饮食"].map((type) => (
                <option key={type}>{type}</option>
              ))}
            </select>
          </Field>
          <Field label="日期">
            <Input
              type="date"
              required
              value={record.date}
              onChange={(event) => setRecord({ ...record, date: event.target.value })}
            />
          </Field>
        </div>
        <Field label="描述">
          <TextArea
            className={textareaClass}
            required
            value={record.description}
            onChange={(event) => setRecord({ ...record, description: event.target.value })}
          />
        </Field>
        {meal ? (
          <>
            <div className="paired-fields">
              <Field label="餐顿（可选）">
                <MealTypeInput
                  value={record.meal_type ?? ""}
                  onChange={(event) => setRecord({ ...record, meal_type: event.target.value })}
                />
              </Field>
              <Field label="时间（可留空）">
                <Input
                  type="time"
                  value={record.time ?? ""}
                  onChange={(event) => setRecord({ ...record, time: event.target.value })}
                />
              </Field>
            </div>
            <div className="form-stack">
              <p className="field-label">食物明细（可选）</p>
              <FoodFields
                foods={record.foods ?? []}
                onChange={(foods) => setRecord({ ...record, foods })}
              />
            </div>
          </>
        ) : (
          <>
            <Field label="金额">
              <Input
                required
                type="number"
                min="0.01"
                step="0.01"
                value={record.amount ?? ""}
                onChange={(event) =>
                  setRecord({
                    ...record,
                    amount: event.target.value ? Number(event.target.value) : null,
                  })
                }
              />
            </Field>
            <div className="paired-fields">
              <Field label="主类别">
                <select
                  className={selectClass}
                  value={record.category ?? ""}
                  onChange={(event) =>
                    setRecord({ ...record, category: event.target.value, subcategory: "" })
                  }
                >
                  <option value="">暂不分类</option>
                  {[
                    ...new Set(
                      [...Object.keys(categoryMap), record.category].filter(
                        (value): value is string => Boolean(value),
                      ),
                    ),
                  ].map((category) => (
                    <option key={category}>{category}</option>
                  ))}
                </select>
              </Field>
              {subcategories.length > 0 && (
                <Field label="子类别">
                  <select
                    className={selectClass}
                    value={record.subcategory ?? ""}
                    onChange={(event) => setRecord({ ...record, subcategory: event.target.value })}
                  >
                    <option value="">请选择</option>
                    {subcategories.map((subcategory) => (
                      <option key={subcategory}>{subcategory}</option>
                    ))}
                  </select>
                </Field>
              )}
            </div>
          </>
        )}
        <Field label="备注（可选）">
          <Input
            value={record.notes ?? ""}
            onChange={(event) => setRecord({ ...record, notes: event.target.value || null })}
          />
        </Field>
        <Button disabled={!record.description.trim() || (!meal && !(Number(record.amount) > 0))}>
          {save.isPending ? "入账中…" : "确认入账"}
        </Button>
      </fieldset>
      <Feedback error={save.error} />
    </form>
  );
}
