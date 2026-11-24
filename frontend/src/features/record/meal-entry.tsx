import { TextArea } from "@radix-ui/themes";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, type MealCreate } from "@/api/client";
import { invalidateMeals } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FoodFields } from "@/features/diet/food-fields";
import { MealTypeInput } from "@/features/diet/meal-type-input";
import { Feedback, Field, textareaClass, today } from "./entry-shared";

type Food = NonNullable<MealCreate["foods"]>[number];
const initialEntry = () => ({
  date: today(),
  time: "",
  meal_type: "",
  description: "",
  notes: "",
  foods: [] as Food[],
});
type SaveRequest = { payload: MealCreate; key: string };

export function MealEntry() {
  const client = useQueryClient();
  const [entry, setEntry] = useState(initialEntry);
  const [pending, setPending] = useState<SaveRequest | null>(null);
  const [message, setMessage] = useState("");
  const save = useMutation({
    mutationFn: ({ payload, key }: SaveRequest) => api.createMeal(payload, key),
    onSuccess: (result) => {
      void invalidateMeals(client);
      setMessage(result.duplicate ? "这条饮食已保存。" : "饮食已记录。");
      setPending(null);
      setEntry(initialEntry());
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (save.isPending) return;
    const payload: MealCreate = {
      ...entry,
      date: entry.date || today(),
      description: entry.description.trim(),
      meal_type: entry.meal_type || null,
      notes: entry.notes.trim() || null,
      foods: entry.foods.filter((food) => food.food_name.trim()),
    };
    const request =
      pending && JSON.stringify(pending.payload) === JSON.stringify(payload)
        ? pending
        : { payload, key: crypto.randomUUID() };
    setPending(request);
    setMessage("");
    save.mutate(request);
  };

  return (
    <form className="content-panel record-composer form-stack" onSubmit={submit}>
      <fieldset className="form-stack manual-fields" disabled={save.isPending}>
        <Field label="吃了什么">
          <TextArea
            required
            className={textareaClass}
            value={entry.description}
            placeholder="例：晚饭在家吃了番茄炒蛋和米饭"
            onChange={(event) => setEntry({ ...entry, description: event.target.value })}
          />
        </Field>
        <details className="manual-options">
          <summary>餐顿、日期、时间与食物明细（可选）</summary>
          <div className="form-stack">
            <div className="entry-fields">
              <Field label="餐顿标签">
                <MealTypeInput
                  value={entry.meal_type}
                  onChange={(event) => setEntry({ ...entry, meal_type: event.target.value })}
                />
              </Field>
              <Field label="日期">
                <Input
                  type="date"
                  value={entry.date}
                  onChange={(event) => setEntry({ ...entry, date: event.target.value })}
                />
              </Field>
              <Field label="时间（可留空）">
                <Input
                  type="time"
                  value={entry.time}
                  onChange={(event) => setEntry({ ...entry, time: event.target.value })}
                />
              </Field>
            </div>
            <FoodFields foods={entry.foods} onChange={(foods) => setEntry({ ...entry, foods })} />
            <Field label="备注">
              <TextArea
                className={textareaClass}
                value={entry.notes}
                onChange={(event) => setEntry({ ...entry, notes: event.target.value })}
              />
            </Field>
          </div>
        </details>
        <Button data-primary-action="true" disabled={!entry.description.trim()}>
          {save.isPending ? "保存中…" : "保存饮食"}
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
