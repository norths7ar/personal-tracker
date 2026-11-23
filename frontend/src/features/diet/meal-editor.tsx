import { TextArea } from "@radix-ui/themes";
import { Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { type Meal, type MealUpdate } from "@/api/client";
import { EditorFooter } from "@/components/record-actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MealTypeInput } from "./meal-type-input";
import { Feedback, Field, textareaClass } from "@/features/record/entry-shared";

export function MealEditor({
  meal,
  saving,
  error,
  onSave,
  onClose,
}: {
  meal: Meal;
  saving: boolean;
  error: Error | null;
  onSave: (payload: MealUpdate) => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState<MealUpdate>({
    date: meal.date,
    time: meal.time ?? "",
    meal_type: meal.meal_type,
    description: meal.description,
    notes: meal.notes,
    foods: meal.foods,
  });
  const updateFood = (index: number, changes: Partial<MealUpdate["foods"][number]>) =>
    setForm({
      ...form,
      foods: form.foods.map((food, foodIndex) =>
        foodIndex === index ? { ...food, ...changes } : food,
      ),
    });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSave({
      ...form,
      description: form.description.trim(),
      notes: form.notes?.trim() || null,
      foods: form.foods.filter((food) => food.food_name.trim()),
    });
  };
  return (
    <form className="form-stack" onSubmit={submit}>
      <div className="paired-fields">
        <Field label="日期">
          <Input
            type="date"
            value={form.date}
            onChange={(event) => setForm({ ...form, date: event.target.value })}
          />
        </Field>
        <Field label="时间">
          <Input
            type="time"
            value={form.time}
            onChange={(event) => setForm({ ...form, time: event.target.value })}
          />
        </Field>
      </div>
      <Field label="餐顿标签">
        <MealTypeInput
          value={form.meal_type ?? ""}
          onChange={(event) => setForm({ ...form, meal_type: event.target.value || null })}
        />
      </Field>
      <Field label="原始描述">
        <TextArea
          className={textareaClass}
          value={form.description}
          onChange={(event) => setForm({ ...form, description: event.target.value })}
        />
      </Field>
      <div className="editor-group">
        <span className="field-label">食物清单</span>
        {form.foods.map((food, index) => (
          <div className="ingredient-list" key={index}>
            <div className="ingredient-row">
              <Input
                value={food.food_name}
                placeholder="食物"
                onChange={(event) => updateFood(index, { food_name: event.target.value })}
              />
              <Input
                value={food.quantity}
                placeholder="份量"
                onChange={(event) => updateFood(index, { quantity: event.target.value })}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() =>
                  setForm({
                    ...form,
                    foods: form.foods.filter((_, itemIndex) => itemIndex !== index),
                  })
                }
              >
                <Trash2 size={15} />
              </Button>
            </div>
            <Input
              value={(food.ingredients ?? []).join("、")}
              placeholder="主要食材"
              onChange={(event) =>
                updateFood(index, {
                  ingredients: splitIngredients(event.target.value),
                })
              }
            />
          </div>
        ))}
      </div>
      <Button
        type="button"
        variant="outline"
        onClick={() =>
          setForm({
            ...form,
            foods: [...form.foods, { food_name: "", quantity: "", ingredients: [] }],
          })
        }
      >
        <Plus size={15} />
        添加食物
      </Button>
      <Field label="备注">
        <TextArea
          className={textareaClass}
          value={form.notes ?? ""}
          onChange={(event) => setForm({ ...form, notes: event.target.value || null })}
        />
      </Field>
      <Feedback error={error} />
      <EditorFooter>
        <Button type="button" variant="outline" disabled={saving} onClick={onClose}>
          取消
        </Button>
        <Button
          disabled={
            saving || !form.description.trim() || !form.foods.some((food) => food.food_name.trim())
          }
        >
          {saving ? "保存中…" : "保存修改"}
        </Button>
      </EditorFooter>
    </form>
  );
}

function splitIngredients(value: string): string[] {
  return value
    .split(/[、,，;；]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
