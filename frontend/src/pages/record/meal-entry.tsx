import { invalidateMeals } from "@/api/invalidate";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { api, type MealCreate, type MealPreparation } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Feedback,
  Field,
  textareaClass,
  today,
} from "@/pages/record/entry-shared";

const initialEntry = (): MealCreate => ({
  date: today(),
  time: "",
  meal_type: null,
  description: "",
  notes: null,
  confidence: null,
  foods: [],
});

export function MealEntry() {
  const queryClient = useQueryClient();
  const [entry, setEntry] = useState<MealCreate>(initialEntry);
  const [review, setReview] = useState<MealPreparation | null>(null);
  const [requestKey, setRequestKey] = useState("");
  const [pendingSave, setPendingSave] = useState<MealCreate | null>(null);
  const [message, setMessage] = useState("");

  const save = useMutation({
    mutationFn: ({ payload, key }: { payload: MealCreate; key: string }) =>
      api.createMeal(payload, key),
    onSuccess: (result) => {
      void invalidateMeals(queryClient);
      setMessage(
        result.duplicate ? "该请求已经保存。" : `已保存饮食 #${result.id}`,
      );
      setReview(null);
      setRequestKey("");
      setPendingSave(null);
      setEntry((current) => ({
        ...current,
        description: "",
        notes: null,
        foods: [],
      }));
    },
  });

  const saveEntry = (payload: MealCreate, key: string) => {
    setPendingSave(payload);
    save.mutate({ payload, key });
  };

  const prepare = useMutation({
    mutationFn: () => api.prepareMeal(entry.description, entry.time),
    onSuccess: (result) => {
      const key = crypto.randomUUID();
      const payload: MealCreate = {
        ...entry,
        meal_type: result.meal_type,
        foods: result.foods,
        confidence: result.confidence,
      };
      setRequestKey(key);
      setEntry(payload);
      if (result.status === "confirmed") {
        saveEntry(payload, key);
      } else {
        setReview(result);
      }
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    setReview(null);
    setPendingSave(null);
    prepare.mutate();
  };

  const updateFood = (
    index: number,
    changes: Partial<MealCreate["foods"][number]>,
  ) => {
    setEntry({
      ...entry,
      foods: entry.foods.map((food, foodIndex) =>
        foodIndex === index ? { ...food, ...changes } : food,
      ),
    });
  };

  const busy = prepare.isPending || save.isPending;

  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-5">
      <form className="space-y-4" onSubmit={submit}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="日期">
            <Input
              type="date"
              value={entry.date}
              onChange={(event) =>
                setEntry({ ...entry, date: event.target.value })
              }
            />
          </Field>
          <Field label="用餐时间">
            <Input
              type="time"
              required
              value={entry.time}
              onChange={(event) =>
                setEntry({ ...entry, time: event.target.value })
              }
            />
          </Field>
        </div>
        <Field label="饮食描述">
          <textarea
            className={textareaClass}
            required
            value={entry.description}
            onChange={(event) =>
              setEntry({ ...entry, description: event.target.value })
            }
            placeholder="例：中午吃了鸡腿饭和一杯豆浆"
          />
        </Field>
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
          data-primary-action={!review}
          disabled={busy || !entry.description.trim() || !entry.time}
        >
          {prepare.isPending ? "分析中…" : save.isPending ? "保存中…" : "提交"}
        </Button>
      </form>

      {review && (
        <div className="mt-5 space-y-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <div>
            <strong>请确认饮食信息</strong>
            <p className="text-sm text-neutral-600">{review.reasoning}</p>
          </div>
          <Field label="餐顿标签">
            <Input
              value={entry.meal_type ?? ""}
              onChange={(event) =>
                setEntry({ ...entry, meal_type: event.target.value || null })
              }
            />
          </Field>
          <div className="space-y-2">
            {entry.foods.map((food, index) => (
              <div
                className="grid gap-2 sm:grid-cols-[1fr_1fr_1.3fr_auto]"
                key={index}
              >
                <Input
                  value={food.food_name}
                  placeholder="食物"
                  onChange={(event) =>
                    updateFood(index, { food_name: event.target.value })
                  }
                />
                <Input
                  value={food.quantity}
                  placeholder="份量"
                  onChange={(event) =>
                    updateFood(index, { quantity: event.target.value })
                  }
                />
                <Input
                  value={(food.ingredients ?? []).join("、")}
                  placeholder="主要食材"
                  onChange={(event) =>
                    updateFood(index, {
                      ingredients: splitIngredients(event.target.value),
                    })
                  }
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() =>
                    setEntry({
                      ...entry,
                      foods: entry.foods.filter(
                        (_, itemIndex) => itemIndex !== index,
                      ),
                    })
                  }
                >
                  <Trash2 size={15} />
                </Button>
              </div>
            ))}
          </div>
          <Button
            type="button"
            variant="outline"
            onClick={() =>
              setEntry({
                ...entry,
                foods: [
                  ...entry.foods,
                  { food_name: "", quantity: "", ingredients: [] },
                ],
              })
            }
          >
            <Plus size={15} />
            添加食物
          </Button>
          <div className="flex gap-2">
            <Button
              data-primary-action="true"
              onClick={() => saveEntry(entry, requestKey)}
              disabled={
                busy || !entry.foods.some((food) => food.food_name.trim())
              }
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

function splitIngredients(value: string): string[] {
  return value
    .split(/[、,，;；]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
