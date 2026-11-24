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
type SaveRequest = {
  signature: string;
  payload: MealCreate;
  key: string;
  autoExtract: boolean;
};

export function MealEntry() {
  const client = useQueryClient();
  const [entry, setEntry] = useState(initialEntry);
  const [pending, setPending] = useState<SaveRequest | null>(null);
  const [message, setMessage] = useState("");
  const save = useMutation({
    mutationFn: async (request: SaveRequest) => {
      let finalPayload = request.payload;
      if (request.autoExtract) {
        try {
          const prep = await api.prepareMeal(
            request.payload.description,
            request.payload.time ?? null,
          );
          const foods = prep.foods.filter((food) => food.food_name.trim());
          finalPayload = {
            ...request.payload,
            meal_type: request.payload.meal_type || prep.meal_type || null,
            foods,
            confidence: prep.confidence,
          };
        } catch {
          finalPayload = request.payload;
        }
        setPending({
          signature: request.signature,
          payload: finalPayload,
          key: request.key,
          autoExtract: false,
        });
      }
      const result = await api.createMeal(finalPayload, request.key);
      return { result, payload: finalPayload };
    },
    onSuccess: ({ result }) => {
      void invalidateMeals(client);
      setMessage(result.duplicate ? "这条饮食已保存。" : "饮食已记录。");
      setPending(null);
      setEntry(initialEntry());
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (save.isPending) return;
    const foods = entry.foods.filter((food) => food.food_name.trim());
    const payload: MealCreate = {
      ...entry,
      date: entry.date || today(),
      time: entry.time || null,
      description: entry.description.trim(),
      meal_type: entry.meal_type || null,
      notes: entry.notes.trim() || null,
      foods,
    };
    const signature = JSON.stringify(payload);
    const request: SaveRequest =
      pending && pending.signature === signature
        ? pending
        : {
            signature,
            payload,
            key: crypto.randomUUID(),
            autoExtract: foods.length === 0,
          };
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
          <summary>餐顿、日期、时间与食物明细</summary>
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
              <Field label="时间">
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
        <div className="composer-footer">
          <Button data-primary-action="true" disabled={save.isPending || !entry.description.trim()}>
            {save.isPending ? "保存中…" : "保存饮食"}
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
