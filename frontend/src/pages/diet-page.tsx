import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import ReactEChartsCore from "echarts-for-react/lib/core";
import { Download, Plus, Trash2 } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import { api, type DietStats, type Meal, type MealUpdate } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const filtered = useMemo(
    () =>
      (meals.data ?? []).filter(
        (meal) =>
          (!startDate || meal.date >= startDate) &&
          (!endDate || meal.date <= endDate),
      ),
    [endDate, meals.data, startDate],
  );
  const selected = meals.data?.find((meal) => meal.id === selectedId) ?? null;

  const update = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: MealUpdate }) =>
      api.updateMeal(id, payload),
    onSuccess: (updated) => {
      queryClient.setQueryData<Meal[]>(["meals"], (current = []) =>
        current.map((meal) => (meal.id === updated.id ? updated : meal)),
      );
      setSelectedId(null);
    },
  });
  const deletion = useMutation({
    mutationFn: api.deleteMeal,
    onSuccess: (_, id) => {
      queryClient.setQueryData<Meal[]>(["meals"], (current = []) =>
        current.filter((meal) => meal.id !== id),
      );
      setSelectedId(null);
    },
  });

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">饮食</h1>
          <p className="mt-1 text-sm text-neutral-500">饮食记录、食材和趋势分析。</p>
        </div>
        {tab === "ledger" && (
          <Button variant="outline" onClick={() => exportMeals(filtered)} disabled={!filtered.length}>
            <Download size={16} />导出当前结果
          </Button>
        )}
      </header>
      <div className="flex gap-1 rounded-lg bg-neutral-200/70 p-1">
        <TabButton active={tab === "ledger"} onClick={() => setTab("ledger")}>查看</TabButton>
        <TabButton active={tab === "analysis"} onClick={() => setTab("analysis")}>分析</TabButton>
      </div>

      {tab === "ledger" ? (
        <>
          <div className="grid gap-3 rounded-lg border border-neutral-200 bg-white p-4 sm:grid-cols-2">
            <Field label="开始日期"><Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></Field>
            <Field label="结束日期"><Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></Field>
          </div>
          {meals.isPending ? <p className="text-sm text-neutral-500">正在读取…</p> : meals.isError ? <Feedback error={meals.error} /> : (
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(360px,0.7fr)]">
              <MealTable meals={filtered} selectedId={selectedId} onSelect={setSelectedId} />
              {selected && (
                <MealEditor
                  key={selected.id}
                  meal={selected}
                  saving={update.isPending}
                  deleting={deletion.isPending}
                  error={update.error ?? deletion.error}
                  onSave={(payload) => update.mutate({ id: selected.id, payload })}
                  onDelete={() => {
                    if (window.confirm(`确定删除饮食记录 #${selected.id} 吗？`)) deletion.mutate(selected.id);
                  }}
                />
              )}
            </div>
          )}
        </>
      ) : (
        <DietAnalysis meals={meals.data ?? []} />
      )}
    </section>
  );
}

function MealTable({ meals, selectedId, onSelect }: { meals: Meal[]; selectedId: number | null; onSelect: (id: number) => void }) {
  if (!meals.length) return <div className="rounded-lg border bg-white p-8 text-center text-neutral-500">该范围内没有饮食记录。</div>;
  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-white">
      <table className="w-full min-w-[700px] text-sm">
        <thead className="bg-neutral-50 text-left text-xs text-neutral-500"><tr><th className="p-3">日期</th><th className="p-3">时间</th><th className="p-3">餐顿</th><th className="p-3">食物</th><th className="p-3">备注</th></tr></thead>
        <tbody>{meals.map((meal) => <tr key={meal.id} onClick={() => onSelect(meal.id)} className={cn("cursor-pointer border-t border-neutral-100", meal.id === selectedId ? "bg-amber-50" : "hover:bg-neutral-50")}><td className="p-3">{meal.date}</td><td className="p-3">{meal.time}</td><td className="p-3">{meal.meal_type || "—"}</td><td className="p-3">{meal.foods.map(foodLabel).join("、")}</td><td className="p-3">{meal.notes || ""}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function MealEditor({ meal, saving, deleting, error, onSave, onDelete }: { meal: Meal; saving: boolean; deleting: boolean; error: Error | null; onSave: (payload: MealUpdate) => void; onDelete: () => void }) {
  const [form, setForm] = useState<MealUpdate>({ date: meal.date, time: meal.time, meal_type: meal.meal_type, description: meal.description, notes: meal.notes, foods: meal.foods });
  const updateFood = (index: number, changes: Partial<MealUpdate["foods"][number]>) => setForm({ ...form, foods: form.foods.map((food, foodIndex) => foodIndex === index ? { ...food, ...changes } : food) });
  const submit = (event: FormEvent) => { event.preventDefault(); onSave({ ...form, description: form.description.trim(), notes: form.notes?.trim() || null, foods: form.foods.filter((food) => food.food_name.trim()) }); };
  return (
    <form className="space-y-4 rounded-lg border border-neutral-200 bg-white p-5" onSubmit={submit}>
      <div><h2 className="font-semibold">编辑记录</h2><p className="text-sm text-neutral-500">#{meal.id}</p></div>
      <div className="grid grid-cols-2 gap-3"><Field label="日期"><Input type="date" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} /></Field><Field label="时间"><Input type="time" value={form.time} onChange={(event) => setForm({ ...form, time: event.target.value })} /></Field></div>
      <Field label="餐顿标签"><Input value={form.meal_type ?? ""} onChange={(event) => setForm({ ...form, meal_type: event.target.value || null })} /></Field>
      <Field label="原始描述"><textarea className={textareaClass} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></Field>
      <div className="space-y-2"><span className="text-sm font-medium">食物清单</span>{form.foods.map((food, index) => <div className="grid gap-2" key={index}><div className="grid grid-cols-[1fr_1fr_auto] gap-2"><Input value={food.food_name} placeholder="食物" onChange={(event) => updateFood(index, { food_name: event.target.value })} /><Input value={food.quantity} placeholder="份量" onChange={(event) => updateFood(index, { quantity: event.target.value })} /><Button type="button" variant="ghost" size="icon" onClick={() => setForm({ ...form, foods: form.foods.filter((_, itemIndex) => itemIndex !== index) })}><Trash2 size={15} /></Button></div><Input value={(food.ingredients ?? []).join("、")} placeholder="主要食材" onChange={(event) => updateFood(index, { ingredients: splitIngredients(event.target.value) })} /></div>)}</div>
      <Button type="button" variant="outline" onClick={() => setForm({ ...form, foods: [...form.foods, { food_name: "", quantity: "", ingredients: [] }] })}><Plus size={15} />添加食物</Button>
      <Field label="备注"><textarea className={textareaClass} value={form.notes ?? ""} onChange={(event) => setForm({ ...form, notes: event.target.value || null })} /></Field>
      <div className="flex flex-wrap gap-2"><Button disabled={saving || !form.description.trim() || !form.foods.some((food) => food.food_name.trim())}>{saving ? "保存中…" : "保存修改"}</Button><Button type="button" variant="danger" disabled={deleting} onClick={onDelete}>{deleting ? "删除中…" : "删除记录"}</Button></div>
      <Feedback error={error} />
    </form>
  );
}

function DietAnalysis({ meals }: { meals: Meal[] }) {
  const months = [...new Set(meals.map((meal) => meal.date.slice(0, 7)))].sort().reverse();
  const [selectedMonth, setSelectedMonth] = useState(months[0] ?? new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit" }).format(new Date()).slice(0, 7));
  const [year, month] = selectedMonth.split("-").map(Number);
  const startDate = `${selectedMonth}-01`;
  const endDate = formatDate(new Date(year!, month!, 0));
  const stats = useQuery({ queryKey: ["diet-stats", startDate, endDate], queryFn: () => api.dietStats(startDate, endDate) });
  if (!months.length) return <div className="rounded-lg border bg-white p-8 text-center text-neutral-500">暂无饮食记录。</div>;
  if (stats.isPending) return <p className="text-sm text-neutral-500">正在分析…</p>;
  if (stats.isError) return <Feedback error={stats.error} />;
  const totalMeals = stats.data.daily_meals.reduce((sum, item) => sum + item.count, 0);
  const daysInMonth = new Date(year!, month!, 0).getDate();
  const topFood = stats.data.food_freq[0]?.food_name ?? "—";
  return (
    <div className="space-y-4">
      <Field label="月份"><select className={`${selectClass} max-w-52`} value={selectedMonth} onChange={(event) => setSelectedMonth(event.target.value)}>{months.map((value) => <option key={value}>{value}</option>)}</select></Field>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Metric label="记录天数" value={`${stats.data.daily_meals.length} / ${daysInMonth}`} /><Metric label="总餐次" value={String(totalMeals)} /><Metric label="期间日均" value={(totalMeals / daysInMonth).toFixed(1)} /><Metric label="最高频食物" value={topFood} /></div>
      <div className="grid gap-4 lg:grid-cols-2"><Chart title="用餐时间分布" option={mealTimeOption(stats.data.meal_times)} /><Chart title="每日餐次" option={{ xAxis: { type: "category", data: stats.data.daily_meals.map((item) => item.date) }, yAxis: { type: "value", minInterval: 1 }, series: [{ type: "line", areaStyle: {}, data: stats.data.daily_meals.map((item) => item.count) }], tooltip: { trigger: "axis" } }} /></div>
      <div className="grid gap-4 lg:grid-cols-2"><Chart title="餐顿标签" option={{ xAxis: { type: "category", data: stats.data.meal_type_dist.map((item) => item.meal_type) }, yAxis: { type: "value", minInterval: 1 }, series: [{ type: "bar", data: stats.data.meal_type_dist.map((item) => item.count) }], tooltip: { trigger: "axis" } }} /><Chart title="高频食物" option={{ yAxis: { type: "category", data: stats.data.food_freq.slice(0, 15).map((item) => item.food_name).reverse() }, xAxis: { type: "value", minInterval: 1 }, series: [{ type: "bar", data: stats.data.food_freq.slice(0, 15).map((item) => item.count).reverse() }], tooltip: { trigger: "axis" } }} /></div>
    </div>
  );
}

function Chart({ title, option }: { title: string; option: object }) { return <div className="rounded-lg border border-neutral-200 bg-white p-4"><h2 className="mb-2 font-medium">{title}</h2><ReactEChartsCore echarts={echarts} option={option} style={{ height: 280 }} /></div>; }
function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border border-neutral-200 bg-white p-4"><p className="text-sm text-neutral-500">{label}</p><p className="mt-1 text-2xl font-semibold">{value}</p></div>; }
function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) { return <button className={cn("flex-1 rounded-md px-3 py-2 text-sm font-medium", active && "bg-white shadow-sm")} onClick={onClick}>{children}</button>; }
function foodLabel(food: Meal["foods"][number]): string { const ingredients = food.ingredients?.length ? `（${food.ingredients.join("、")}）` : ""; return `${food.food_name}${food.quantity ? `×${food.quantity}` : ""}${ingredients}`; }
function splitIngredients(value: string): string[] { return value.split(/[、,，;；]/).map((item) => item.trim()).filter(Boolean); }
function formatDate(value: Date): string { return new Intl.DateTimeFormat("en-CA").format(value); }
function mealTimeOption(rows: DietStats["meal_times"]) { return { tooltip: { formatter: (params: { data: [string, number, string] }) => `${params.data[0]} ${params.data[2]}` }, xAxis: { type: "category", data: [...new Set(rows.map((item) => item.date))] }, yAxis: { type: "value", min: 0, max: 24, interval: 4, axisLabel: { formatter: (value: number) => `${String(value).padStart(2, "0")}:00` } }, series: [{ type: "scatter", symbolSize: 9, data: rows.map((item) => { const [hour = 0, minute = 0] = item.time.split(":").map(Number); return [item.date, hour + minute / 60, item.time] as [string, number, string]; }) }] }; }
function exportMeals(meals: Meal[]) { const rows = [["ID", "日期", "时间", "餐顿", "描述", "食物", "备注"], ...meals.map((meal) => [meal.id, meal.date, meal.time, meal.meal_type ?? "", meal.description, meal.foods.map(foodLabel).join("、"), meal.notes ?? ""])]; const csv = rows.map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\r\n"); const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" })); link.download = "diet.csv"; link.click(); URL.revokeObjectURL(link.href); }
