import "./food-fields.css";
import { Plus, Trash2 } from "lucide-react";
import type { Meal } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field } from "@/features/record/entry-shared";

type Food = Meal["foods"][number];

export function FoodFields({
  foods,
  onChange,
}: {
  foods: Food[];
  onChange: (foods: Food[]) => void;
}) {
  const update = (index: number, changes: Partial<Food>) =>
    onChange(foods.map((food, i) => (i === index ? { ...food, ...changes } : food)));
  return (
    <div className="form-stack">
      {foods.map((food, index) => (
        <div className="ingredient-list" key={index}>
          <div className="ingredient-row">
            <Field label="食物名称">
              <Input
                aria-label={`食物名称 ${index + 1}`}
                value={food.food_name}
                placeholder="例：番茄炒蛋"
                onChange={(event) => update(index, { food_name: event.target.value })}
              />
            </Field>
            <Field label="份量">
              <Input
                aria-label={`份量 ${index + 1}`}
                value={food.quantity}
                placeholder="例：一小碗"
                onChange={(event) => update(index, { quantity: event.target.value })}
              />
            </Field>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`移除食物 ${index + 1}`}
              onClick={() => onChange(foods.filter((_, i) => i !== index))}
            >
              <Trash2 size={15} />
            </Button>
          </div>
          <Field label="主要食材">
            <Input
              aria-label={`主要食材 ${index + 1}`}
              value={(food.ingredients ?? []).join("、")}
              placeholder="例：番茄、鸡蛋"
              onChange={(event) =>
                update(index, {
                  ingredients: event.target.value
                    .split(/[、,，;；]/)
                    .map((item) => item.trim())
                    .filter(Boolean),
                })
              }
            />
          </Field>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        onClick={() => onChange([...foods, { food_name: "", quantity: "", ingredients: [] }])}
      >
        <Plus size={15} />
        添加食物明细
      </Button>
    </div>
  );
}
