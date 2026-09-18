import { invalidateMeals } from "@/api/invalidate";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { Download, Plus, Trash2 } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import {
  api,
  type DietStats,
  type Meal,
  type MealUpdate,
  type MealBulkChanges,
} from "@/api/client";
import {
  RecordActions,
  BulkFieldToggle,
  EditorFooter,
} from "@/components/record-actions";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { EChart } from "@/components/echart";
import { Input } from "@/components/ui/input";
import { useRecordSelection } from "@/lib/use-record-selection";
import { cn } from "@/lib/utils";
import {
  Feedback,
  Field,
  selectClass,
  textareaClass,
} from "@/pages/record/entry-shared";

type Tab = "ledger" | "analysis";

echarts.use([
  BarChart,
  LineChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  CanvasRenderer,
]);

export function DietPage() {
  const queryClient = useQueryClient();
  const meals = useQuery({ queryKey: ["meals"], queryFn: api.meals });
  const [tab, setTab] = useState<Tab>("ledger");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [page, setPage] = useState(0);
  const { rowSelection, setRowSelection, selectedIds, rowEvents } =
    useRecordSelection();
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
  const selected = (meals.data ?? []).filter((meal) =>
    selectedIds.includes(meal.id),
  );
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
    if (
      selectedIds.length &&
      window.confirm(`确定删除选中的 ${selectedIds.length} 条饮食记录吗？`)
    )
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
    <section className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            饮食
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            饮食记录、食材和趋势分析。
          </p>
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
      <div className="flex gap-1 rounded-lg bg-neutral-200/70 p-1">
        <TabButton
          active={tab === "ledger"}
          onClick={() => {
            setTab("ledger");
            setRowSelection({});
          }}
        >
          查看
        </TabButton>
        <TabButton
          active={tab === "analysis"}
          onClick={() => {
            setTab("analysis");
            setRowSelection({});
          }}
        >
          分析
        </TabButton>
      </div>
      {tab === "ledger" ? (
        <>
          <div className="grid gap-3 rounded-lg border border-neutral-200 bg-white p-4 sm:grid-cols-[176px_176px]">
            <Field label="开始日期">
              <Input
                type="date"
                value={startDate}
                max={endDate || undefined}
                onChange={(event) =>
                  selectDate(event.target.value, setStartDate)
                }
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
              <p role="alert" className="text-sm text-red-600 sm:col-span-2">
                开始日期不能晚于结束日期。
              </p>
            )}
          </div>
          {meals.isPending ? (
            <p className="text-sm text-neutral-500">正在读取…</p>
          ) : meals.isError ? (
            <Feedback error={meals.error} />
          ) : (
            <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
              <div className="flex items-center justify-between gap-3 border-b border-neutral-200 px-4 py-3 text-sm text-neutral-500">
                <span>共 {filtered.length} 条</span>
                <div className="flex items-center gap-2">
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
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-sm">
                  <thead className="bg-neutral-50 text-left text-xs text-neutral-500">
                    <tr>
                      <th className="w-10 p-3">
                        <Checkbox
                          aria-label="选择当前页"
                          disabled={!visible.length}
                          checked={
                            visible.length > 0 &&
                            (visible.every((meal) => rowSelection[meal.id]) ||
                              (visible.some((meal) => rowSelection[meal.id]) &&
                                "indeterminate"))
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
                      <th className="p-3">日期</th>
                      <th className="p-3">时间</th>
                      <th className="p-3">餐顿</th>
                      <th className="p-3">食物</th>
                      <th className="w-48 whitespace-nowrap p-3">备注</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((meal) => (
                      <tr
                        key={meal.id}
                        aria-selected={Boolean(rowSelection[meal.id])}
                        {...rowEvents(meal.id, () => openEditor(meal))}
                        className={cn(
                          "cursor-pointer border-t border-neutral-100",
                          rowSelection[meal.id]
                            ? "bg-amber-50"
                            : "hover:bg-neutral-50",
                        )}
                      >
                        <td className="p-3">
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
                        <td className="w-32 whitespace-nowrap p-3">
                          {meal.date}
                        </td>
                        <td className="w-24 whitespace-nowrap p-3">
                          {meal.time || "—"}
                        </td>
                        <td className="w-24 whitespace-nowrap p-3">
                          {meal.meal_type || "—"}
                        </td>
                        <td className="p-3">
                          {meal.foods.map(foodLabel).join("、")}
                        </td>
                        <td className="w-48 break-words p-3">
                          {meal.notes || ""}
                        </td>
                      </tr>
                    ))}
                    {!visible.length && (
                      <tr>
                        <td
                          colSpan={6}
                          className="p-8 text-center text-neutral-500"
                        >
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
            onEdit={() =>
              selected.length === 1
                ? openEditor(selected[0]!)
                : setBulkEditing(true)
            }
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
              <DialogDescription>
                修改日期、食物与备注，保存后生效。
              </DialogDescription>
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
        <BulkMealEditor
          meals={selected}
          onClose={() => setBulkEditing(false)}
          onSaved={refresh}
        />
      )}
    </section>
  );
}

function BulkMealEditor({
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
          className="space-y-4"
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
          ).map(([key, label]) => (
            <div key={key} className="space-y-2">
              <BulkFieldToggle
                label={`修改${label}`}
                checked={Boolean(enabled[key])}
                onChange={(checked) =>
                  setEnabled({ ...enabled, [key]: checked })
                }
              />
              <Input
                aria-label={label}
                type={key === "date" || key === "time" ? key : "text"}
                value={values[key]}
                disabled={!enabled[key]}
                required={
                  Boolean(enabled[key]) && (key === "date" || key === "time")
                }
                placeholder={
                  key === "notes" || key === "meal_type"
                    ? "留空将清除所选记录的此字段"
                    : undefined
                }
                onChange={(event) =>
                  setValues({ ...values, [key]: event.target.value })
                }
              />
            </div>
          ))}
          <Feedback error={update.error} />
          <EditorFooter>
            <Button
              type="button"
              variant="outline"
              disabled={update.isPending}
              onClick={onClose}
            >
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

function MealEditor({
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
  const updateFood = (
    index: number,
    changes: Partial<MealUpdate["foods"][number]>,
  ) =>
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
    <form className="space-y-4" onSubmit={submit}>
      <div className="grid grid-cols-2 gap-3">
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
        <Input
          value={form.meal_type ?? ""}
          onChange={(event) =>
            setForm({ ...form, meal_type: event.target.value || null })
          }
        />
      </Field>
      <Field label="原始描述">
        <textarea
          className={textareaClass}
          value={form.description}
          onChange={(event) =>
            setForm({ ...form, description: event.target.value })
          }
        />
      </Field>
      <div className="space-y-2">
        <span className="text-sm font-medium">食物清单</span>
        {form.foods.map((food, index) => (
          <div className="grid gap-2" key={index}>
            <div className="grid grid-cols-[1fr_1fr_auto] gap-2">
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
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() =>
                  setForm({
                    ...form,
                    foods: form.foods.filter(
                      (_, itemIndex) => itemIndex !== index,
                    ),
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
            foods: [
              ...form.foods,
              { food_name: "", quantity: "", ingredients: [] },
            ],
          })
        }
      >
        <Plus size={15} />
        添加食物
      </Button>
      <Field label="备注">
        <textarea
          className={textareaClass}
          value={form.notes ?? ""}
          onChange={(event) =>
            setForm({ ...form, notes: event.target.value || null })
          }
        />
      </Field>
      <Feedback error={error} />
      <EditorFooter>
        <Button
          type="button"
          variant="outline"
          disabled={saving}
          onClick={onClose}
        >
          取消
        </Button>
        <Button
          disabled={
            saving ||
            !form.description.trim() ||
            !form.foods.some((food) => food.food_name.trim())
          }
        >
          {saving ? "保存中…" : "保存修改"}
        </Button>
      </EditorFooter>
    </form>
  );
}

function DietAnalysis({ meals }: { meals: Meal[] }) {
  const months = [...new Set(meals.map((meal) => meal.date.slice(0, 7)))]
    .sort()
    .reverse();
  const today = formatDate(new Date());
  const [selectedMonth, setSelectedMonth] = useState(
    months[0] ?? today.slice(0, 7),
  );
  const [year, month] = selectedMonth.split("-").map(Number);
  const startDate = `${selectedMonth}-01`;
  const monthEnd = formatDate(new Date(year!, month!, 0));
  const endDate = monthEnd < today ? monthEnd : today;
  const days = Array.from(
    {
      length: selectedMonth > today.slice(0, 7) ? 0 : Number(endDate.slice(-2)),
    },
    (_, index) => `${selectedMonth}-${String(index + 1).padStart(2, "0")}`,
  );
  const stats = useQuery({
    queryKey: ["diet-stats", startDate, endDate],
    queryFn: () => api.dietStats(startDate, endDate),
  });
  if (!months.length)
    return (
      <div className="rounded-lg border bg-white p-8 text-center text-neutral-500">
        暂无饮食记录。
      </div>
    );
  if (stats.isPending)
    return <p className="text-sm text-neutral-500">正在分析…</p>;
  if (stats.isError) return <Feedback error={stats.error} />;
  const totalRecords = stats.data.daily_meals.reduce(
    (sum, item) => sum + item.count,
    0,
  );
  const dailyCounts = new Map(
    stats.data.daily_meals.map((item) => [item.date, item.count]),
  );
  const topFood = stats.data.food_freq[0]?.food_name ?? "—";
  return (
    <div className="space-y-4">
      <Field label="月份">
        <select
          className={`${selectClass} max-w-52`}
          value={selectedMonth}
          onChange={(event) => setSelectedMonth(event.target.value)}
        >
          {months.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </Field>
      <p className="text-sm text-neutral-500">
        {days.length
          ? `统计范围：${startDate} 至 ${endDate}，共 ${days.length} 天。`
          : "所选期间尚未开始。"}
        按记录次数统计，零食记录不视为一餐；未记录不代表没有进食。
      </p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="记录天数 / 期间天数"
          value={`${stats.data.daily_meals.length} / ${days.length}`}
        />
        <Metric label="饮食记录次数" value={String(totalRecords)} />
        <Metric
          label={`日均记录次数（按 ${days.length} 天）`}
          value={days.length ? (totalRecords / days.length).toFixed(1) : "—"}
        />
        <Metric label="最高频食物" value={topFood} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Chart
          title="用餐时间分布"
          description="从上到下由早到晚，仅展示已记录的时间。"
          option={mealTimeOption(stats.data.meal_times, days)}
        />
        <Chart
          title="每日饮食记录次数"
          description="断点表示当天未记录，不计为进食 0 次。"
          option={{
            grid: { left: 40, right: 16, top: 24, bottom: 32 },
            xAxis: {
              type: "category",
              data: days,
              axisLabel: { formatter: (value: string) => value.slice(5) },
            },
            yAxis: { type: "value", min: 0, minInterval: 1 },
            series: [
              {
                type: "line",
                connectNulls: false,
                showSymbol: true,
                showAllSymbol: true,
                symbol: "circle",
                symbolSize: 7,
                data: days.map((day) => dailyCounts.get(day) ?? null),
              },
            ],
            tooltip: { trigger: "axis" },
          }}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Chart
          title="高频食物"
          description="按食物／菜名原文统计出现次数，不合并相似名称。"
          option={frequencyOption(
            stats.data.food_freq.map((item) => ({
              name: item.food_name,
              count: item.count,
            })),
          )}
        />
        <Chart
          title="高频食材"
          description={`${totalRecords} 条记录中有 ${stats.data.ingredient_record_count} 条包含食材。同一食材每条记录只计一次；未填写食材不代表未食用。`}
          empty={!stats.data.ingredient_freq.length}
          option={frequencyOption(
            stats.data.ingredient_freq.map((item) => ({
              name: item.ingredient_name,
              count: item.count,
            })),
          )}
        />
      </div>
    </div>
  );
}

function Chart({
  title,
  description,
  option,
  empty = false,
}: {
  title: string;
  description: string;
  option: object;
  empty?: boolean;
}) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-4">
      <h2 className="font-medium">{title}</h2>
      <p className="mb-2 mt-1 min-h-10 text-xs leading-5 text-neutral-500">
        {description}
      </p>
      {empty ? (
        <p className="flex h-[280px] items-center justify-center text-sm text-neutral-500">
          该期间尚无食材数据。
        </p>
      ) : (
        <EChart option={option} />
      )}
    </div>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-4">
      <p className="text-sm text-neutral-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}
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
    <button
      className={cn(
        "flex-1 rounded-md px-3 py-2 text-sm font-medium",
        active && "bg-white shadow-sm",
      )}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
function foodLabel(food: Meal["foods"][number]): string {
  return `${food.food_name}${food.quantity ? `×${food.quantity}` : ""}`;
}
function splitIngredients(value: string): string[] {
  return value
    .split(/[、,，;；]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
function formatDate(value: Date): string {
  return new Intl.DateTimeFormat("en-CA").format(value);
}
function mealTimeOption(rows: DietStats["meal_times"], days: string[]) {
  return {
    grid: { left: 48, right: 16, top: 24, bottom: 32 },
    tooltip: {
      formatter: (params: { data: [string, number, string] }) =>
        `${params.data[0]} ${params.data[2]}`,
    },
    xAxis: {
      type: "category",
      data: days,
      axisLabel: { formatter: (value: string) => value.slice(5) },
    },
    yAxis: {
      type: "value",
      inverse: true,
      min: 0,
      max: 24,
      interval: 4,
      axisLabel: {
        formatter: (value: number) => `${String(value).padStart(2, "0")}:00`,
      },
    },
    series: [
      {
        type: "scatter",
        symbolSize: 9,
        data: rows.map((item) => {
          const [hour = 0, minute = 0] = item.time.split(":").map(Number);
          return [item.date, hour + minute / 60, item.time] as [
            string,
            number,
            string,
          ];
        }),
      },
    ],
  };
}
function frequencyOption(rows: { name: string; count: number }[]) {
  const visible = rows.slice(0, 10);
  return {
    grid: { left: 12, right: 32, top: 16, bottom: 24, containLabel: true },
    yAxis: {
      type: "category",
      inverse: true,
      data: visible.map((item) => item.name),
      axisLabel: { width: 120, overflow: "truncate" },
    },
    xAxis: { type: "value", minInterval: 1 },
    series: [
      {
        type: "bar",
        barMaxWidth: 18,
        label: { show: true, position: "right" },
        data: visible.map((item) => item.count),
      },
    ],
    tooltip: { trigger: "axis" },
  };
}
function exportMeals(meals: Meal[]) {
  const rows = [
    ["ID", "日期", "时间", "餐顿", "描述", "食物", "备注"],
    ...meals.map((meal) => [
      meal.id,
      meal.date,
      meal.time,
      meal.meal_type ?? "",
      meal.description,
      meal.foods
        .map(
          (food) =>
            `${foodLabel(food)}${food.ingredients?.length ? `（${food.ingredients.join("、")}）` : ""}`,
        )
        .join("、"),
      meal.notes ?? "",
    ]),
  ];
  const csv = rows
    .map((row) =>
      row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","),
    )
    .join("\r\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(
    new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }),
  );
  link.download = "diet.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}
