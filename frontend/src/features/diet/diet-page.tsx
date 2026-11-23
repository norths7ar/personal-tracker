import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import { api, type Meal, type MealUpdate } from "@/api/client";
import { invalidateMeals } from "@/api/invalidate";
import { RecordActions } from "@/components/record-actions";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@radix-ui/themes";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useRecordSelection } from "@/lib/use-record-selection";
import { cn } from "@/lib/utils";
import { Feedback, Field } from "@/features/record/entry-shared";
import { exportMeals, foodLabel } from "./utils";
import { DietAnalysis } from "./diet-analysis";
import { MealEditor } from "./meal-editor";
import { BulkMealEditor } from "./bulk-editor";
import "./diet-page.css";

export function DietPage() {
  const queryClient = useQueryClient();
  const meals = useQuery({ queryKey: ["diet", "meals"], queryFn: api.meals });
  const [tab, setTab] = useState<Tab>("ledger");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [page, setPage] = useState(0);
  const { rowSelection, setRowSelection, selectedIds, rowEvents } = useRecordSelection();
  const [editing, setEditing] = useState<Meal | null>(null);
  const [bulkEditing, setBulkEditing] = useState(false);
  const invalidRange = Boolean(startDate && endDate && startDate > endDate);
  const filtered = useMemo(
    () =>
      (meals.data ?? []).filter(
        (meal) =>
          !invalidRange &&
          (!startDate || meal.date >= startDate) &&
          (!endDate || meal.date <= endDate),
      ),
    [meals.data, startDate, endDate, invalidRange],
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / 50));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(currentPage * 50, (currentPage + 1) * 50);
  const selected = (meals.data ?? []).filter((meal) => selectedIds.includes(meal.id));
  const refresh = () => {
    void invalidateMeals(queryClient);
    setEditing(null);
    setBulkEditing(false);
    setRowSelection({});
  };
  const update = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: MealUpdate }) =>
      api.updateMeal(id, payload),
    onSuccess: refresh,
  });
  const deletion = useMutation({
    mutationFn: api.deleteMeals,
    onSuccess: refresh,
  });
  const deleteSelected = () => {
    if (selectedIds.length && window.confirm(`确定删除选中的 ${selectedIds.length} 条饮食记录吗？`))
      deletion.mutate(selectedIds);
  };
  const openEditor = (meal: Meal) => {
    update.reset();
    setEditing(meal);
  };
  const selectDate = (value: string, setter: (value: string) => void) => {
    setter(value);
    setPage(0);
    setRowSelection({});
  };
  return (
    <section className="page-stack diet-page">
      <header className="page-heading">
        <div>
          <h1 className="page-title">饮食</h1>
        </div>
        {tab === "ledger" && (
          <Button
            variant="outline"
            onClick={() => exportMeals(filtered)}
            disabled={!filtered.length}
          >
            <Download size={16} />
            导出当前结果
          </Button>
        )}
      </header>
      <div className="page-tabs">
        <TabButton
          active={tab === "ledger"}
          onClick={() => {
            setTab("ledger");
            setRowSelection({});
          }}
        >
          饮食记录
        </TabButton>
        <TabButton
          active={tab === "analysis"}
          onClick={() => {
            setTab("analysis");
            setRowSelection({});
          }}
        >
          饮食分析
        </TabButton>
      </div>
      {tab === "ledger" ? (
        <>
          <div className="diet-filters">
            <Field label="开始日期">
              <Input
                type="date"
                value={startDate}
                max={endDate || undefined}
                onChange={(event) => selectDate(event.target.value, setStartDate)}
              />
            </Field>
            <Field label="结束日期">
              <Input
                type="date"
                value={endDate}
                min={startDate || undefined}
                onChange={(event) => selectDate(event.target.value, setEndDate)}
              />
            </Field>
            {invalidRange && (
              <p role="alert" className="filter-error">
                开始日期不能晚于结束日期。
              </p>
            )}
          </div>
          {meals.isPending ? (
            <p className="muted-text">正在读取…</p>
          ) : meals.isError ? (
            <Feedback error={meals.error} />
          ) : (
            <div className="table-panel">
              <div className="table-toolbar">
                <span>共 {filtered.length} 条</span>
                <div className="pagination-controls">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!currentPage}
                    onClick={() => setPage(currentPage - 1)}
                  >
                    上一页
                  </Button>
                  <span>
                    第 {currentPage + 1} / {pageCount} 页
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={currentPage + 1 >= pageCount}
                    onClick={() => setPage(currentPage + 1)}
                  >
                    下一页
                  </Button>
                </div>
              </div>
              <div className="table-scroll">
                <table className="diet-table">
                  <thead className="data-table-heading">
                    <tr>
                      <th className="diet-selection-cell">
                        <Checkbox
                          aria-label="选择当前页"
                          disabled={!visible.length}
                          checked={
                            visible.length > 0 &&
                            (visible.every((meal) => rowSelection[meal.id]) ||
                              (visible.some((meal) => rowSelection[meal.id]) && "indeterminate"))
                          }
                          onCheckedChange={(checked) =>
                            setRowSelection((current) => {
                              const next = { ...current };
                              visible.forEach((meal) => {
                                if (checked) next[meal.id] = true;
                                else delete next[meal.id];
                              });
                              return next;
                            })
                          }
                        />
                      </th>
                      <th className="data-cell">日期</th>
                      <th className="data-cell">时间</th>
                      <th className="data-cell">餐顿</th>
                      <th className="data-cell">食物</th>
                      <th className="diet-foods-cell">备注</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((meal) => (
                      <tr
                        key={meal.id}
                        aria-selected={Boolean(rowSelection[meal.id])}
                        {...rowEvents(meal.id, () => openEditor(meal))}
                        className={cn(
                          "selectable-row",
                          rowSelection[meal.id] ? "row-selected" : "row-interactive",
                        )}
                      >
                        <td className="data-cell">
                          <Checkbox
                            aria-label={`选择记录 ${meal.id}`}
                            checked={Boolean(rowSelection[meal.id])}
                            onCheckedChange={(checked) =>
                              setRowSelection((current) => ({
                                ...current,
                                [meal.id]: Boolean(checked),
                              }))
                            }
                          />
                        </td>
                        <td className="diet-date-cell">{meal.date}</td>
                        <td className="diet-time-cell">{meal.time || "—"}</td>
                        <td className="diet-time-cell">{meal.meal_type || "—"}</td>
                        <td className="data-cell">{meal.foods.map(foodLabel).join("、")}</td>
                        <td className="diet-note-cell">{meal.notes || ""}</td>
                      </tr>
                    ))}
                    {!visible.length && (
                      <tr>
                        <td colSpan={6} className="table-empty">
                          该范围内没有饮食记录。
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          <RecordActions
            count={selectedIds.length}
            busy={deletion.isPending}
            error={deletion.error}
            onEdit={() => (selected.length === 1 ? openEditor(selected[0]!) : setBulkEditing(true))}
            onDelete={deleteSelected}
            onClear={() => setRowSelection({})}
          />
        </>
      ) : (
        <DietAnalysis meals={meals.data ?? []} />
      )}
      <Dialog
        open={Boolean(editing)}
        onOpenChange={(open) => {
          if (!open && !update.isPending) setEditing(null);
        }}
      >
        {editing && (
          <DialogContent layout="center">
            <DialogHeader>
              <DialogTitle>编辑饮食记录</DialogTitle>
              <DialogDescription>修改日期、食物与备注，保存后生效。</DialogDescription>
            </DialogHeader>
            <MealEditor
              key={editing.id}
              meal={editing}
              saving={update.isPending}
              error={update.error}
              onSave={(payload) => update.mutate({ id: editing.id, payload })}
              onClose={() => setEditing(null)}
            />
          </DialogContent>
        )}
      </Dialog>
      {bulkEditing && (
        <BulkMealEditor meals={selected} onClose={() => setBulkEditing(false)} onSaved={refresh} />
      )}
    </section>
  );
}

type Tab = "ledger" | "analysis";

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button className={cn("page-tab", active && "page-tab-selected")} onClick={onClick}>
      {children}
    </button>
  );
}
