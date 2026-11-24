import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Meal, type MealBulkChanges } from "@/api/client";
import { BulkFieldToggle, EditorFooter } from "@/components/record-actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { MealTypeInput } from "./meal-type-input";
import { Feedback } from "@/features/record/entry-shared";

export function BulkMealEditor({
  meals,
  onClose,
  onSaved,
}: {
  meals: Meal[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [values, setValues] = useState({
    date: "",
    time: "",
    meal_type: "",
    notes: "",
  });
  const changes = Object.fromEntries(
    Object.entries(values)
      .filter(([key]) => enabled[key])
      .map(([key, value]) => [key, value || null]),
  ) as MealBulkChanges;
  const update = useMutation({
    mutationFn: () =>
      api.updateMeals(
        meals.map((meal) => meal.id),
        changes,
      ),
    onSuccess: onSaved,
  });
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !update.isPending) onClose();
      }}
    >
      <DialogContent layout="center">
        <DialogHeader>
          <DialogTitle>编辑 {meals.length} 条饮食记录</DialogTitle>
          <DialogDescription>
            仅修改勾选的字段；原始描述、食物及食材清单保持不变。
          </DialogDescription>
        </DialogHeader>
        <form
          className="form-stack"
          onSubmit={(event) => {
            event.preventDefault();
            update.mutate();
          }}
        >
          {(
            [
              ["date", "日期"],
              ["time", "时间"],
              ["meal_type", "餐顿标签"],
              ["notes", "备注"],
            ] as const
          ).map(([key, label]) => {
            const FieldInput = key === "meal_type" ? MealTypeInput : Input;
            return (
              <div key={key} className="editor-group">
                <BulkFieldToggle
                  label={`修改${label}`}
                  checked={Boolean(enabled[key])}
                  onChange={(checked) => setEnabled({ ...enabled, [key]: checked })}
                />
                <FieldInput
                  aria-label={label}
                  type={key === "date" || key === "time" ? key : "text"}
                  value={values[key]}
                  disabled={!enabled[key]}
                  required={Boolean(enabled[key]) && key === "date"}
                  placeholder={
                    key === "notes" || key === "meal_type" || key === "time"
                      ? "留空将清除所选记录的此字段"
                      : undefined
                  }
                  onChange={(event) => setValues({ ...values, [key]: event.target.value })}
                />
              </div>
            );
          })}
          <Feedback error={update.error} />
          <EditorFooter>
            <Button type="button" variant="outline" disabled={update.isPending} onClick={onClose}>
              取消
            </Button>
            <Button disabled={update.isPending || !Object.keys(changes).length}>
              {update.isPending ? "保存中…" : `修改 ${meals.length} 条记录`}
            </Button>
          </EditorFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
