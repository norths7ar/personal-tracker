import { invalidateFinance } from "@/api/invalidate";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import {
  api,
  type ConfirmExpected,
  type ExpectedRecord,
  type ExpectedWrite,
  type PrepaidRecord,
  type PrepaidUpdate,
  type PrepaidWrite,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  Feedback,
  Field,
  selectClass,
  textareaClass,
  today,
} from "@/pages/record/entry-shared";

type Tab = "expected" | "prepaid";
type ExpectedAction =
  { mode: "create" } | { mode: "edit" | "confirm"; record: ExpectedRecord };
type PrepaidAction =
  { mode: "create" } | { mode: "edit"; record: PrepaidRecord };

export function CrossPeriodPage() {
  const [tab, setTab] = useState<Tab>("expected");
  const [expectedAction, setExpectedAction] = useState<ExpectedAction | null>(
    null,
  );
  const [prepaidAction, setPrepaidAction] = useState<PrepaidAction | null>(
    null,
  );
  const data = useQuery({
    queryKey: ["cross-period"],
    queryFn: api.crossPeriod,
  });

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            跨期费用
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            管理预计支出、周期付款和预付摊销。
          </p>
        </div>
        <Button
          onClick={() =>
            tab === "expected"
              ? setExpectedAction({ mode: "create" })
              : setPrepaidAction({ mode: "create" })
          }
        >
          <Plus size={16} />
          {tab === "expected" ? "新增预计支出" : "新增预付摊销"}
        </Button>
      </header>
      <div className="flex gap-1 rounded-lg bg-neutral-200/70 p-1">
        <TabButton
          active={tab === "expected"}
          onClick={() => setTab("expected")}
        >
          预计支出
        </TabButton>
        <TabButton active={tab === "prepaid"} onClick={() => setTab("prepaid")}>
          预付摊销
        </TabButton>
      </div>
      {data.isPending ? (
        <p className="text-sm text-neutral-500">正在读取…</p>
      ) : data.isError ? (
        <Feedback error={data.error} />
      ) : tab === "expected" ? (
        <ExpectedTable
          records={data.data.expected}
          onAction={setExpectedAction}
        />
      ) : (
        <PrepaidTable records={data.data.prepaid} onAction={setPrepaidAction} />
      )}

      <Dialog
        open={expectedAction !== null}
        onOpenChange={(open) => !open && setExpectedAction(null)}
      >
        <DialogContent>
          {expectedAction && (
            <ExpectedForm
              action={expectedAction}
              onDone={() => setExpectedAction(null)}
            />
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={prepaidAction !== null}
        onOpenChange={(open) => !open && setPrepaidAction(null)}
      >
        <DialogContent>
          {prepaidAction && (
            <PrepaidForm
              action={prepaidAction}
              onDone={() => setPrepaidAction(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function ExpectedTable({
  records,
  onAction,
}: {
  records: ExpectedRecord[];
  onAction: (action: ExpectedAction) => void;
}) {
  const queryClient = useQueryClient();
  const deletion = useMutation({
    mutationFn: api.deleteExpected,
    onSuccess: () => invalidateFinance(queryClient),
  });
  if (!records.length) return <Empty text="暂无预计支出。" />;
  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-white">
      <table className="w-full min-w-[820px] text-sm">
        <thead className="bg-neutral-50 text-left text-xs text-neutral-500">
          <tr>
            <th className="p-3">描述</th>
            <th className="p-3">金额</th>
            <th className="p-3">付款日</th>
            <th className="p-3">周期</th>
            <th className="p-3">分类</th>
            <th className="p-3">状态</th>
            <th className="p-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr
              className="border-t border-neutral-100"
              key={`${record.source}-${record.id}`}
            >
              <td className="p-3 font-medium">{record.description}</td>
              <td className="p-3">{money(record.amount)}</td>
              <td className="p-3">{record.next_date || "—"}</td>
              <td className="p-3">{record.cycle}</td>
              <td className="p-3">{categoryLabel(record)}</td>
              <td className="p-3">
                <StateBadge state={record.state} />
              </td>
              <td className="p-3">
                <div className="flex justify-end gap-1">
                  <Button
                    size="sm"
                    onClick={() => onAction({ mode: "confirm", record })}
                  >
                    <Check size={14} />
                    入账
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => onAction({ mode: "edit", record })}
                  >
                    <Pencil size={15} />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    disabled={deletion.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          `确认删除“${record.description}”？历史流水不会受影响。`,
                        )
                      )
                        deletion.mutate(record);
                    }}
                  >
                    <Trash2 size={15} />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Feedback error={deletion.error} />
    </div>
  );
}

function PrepaidTable({
  records,
  onAction,
}: {
  records: PrepaidRecord[];
  onAction: (action: PrepaidAction) => void;
}) {
  const queryClient = useQueryClient();
  const deletion = useMutation({
    mutationFn: api.deletePrepaid,
    onSuccess: () => invalidateFinance(queryClient),
  });
  if (!records.length) return <Empty text="暂无预付摊销。" />;
  return (
    <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-white">
      <table className="w-full min-w-[760px] text-sm">
        <thead className="bg-neutral-50 text-left text-xs text-neutral-500">
          <tr>
            <th className="p-3">描述</th>
            <th className="p-3">总金额</th>
            <th className="p-3">月均</th>
            <th className="p-3">剩余月数</th>
            <th className="p-3">摊销开始</th>
            <th className="p-3">分类</th>
            <th className="p-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr className="border-t border-neutral-100" key={record.id}>
              <td className="p-3 font-medium">{record.description}</td>
              <td className="p-3">{money(record.amount)}</td>
              <td className="p-3">{money(record.monthly_equivalent)}</td>
              <td className="p-3">{record.remaining_months}</td>
              <td className="p-3">{record.start_month}</td>
              <td className="p-3">{categoryLabel(record)}</td>
              <td className="p-3">
                <div className="flex justify-end gap-1">
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => onAction({ mode: "edit", record })}
                  >
                    <Pencil size={15} />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    disabled={deletion.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          `确认删除“${record.description}”的摊销设置？关联流水不会删除。`,
                        )
                      )
                        deletion.mutate(record.id);
                    }}
                  >
                    <Trash2 size={15} />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Feedback error={deletion.error} />
    </div>
  );
}

function ExpectedForm({
  action,
  onDone,
}: {
  action: ExpectedAction;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: api.categories,
  });
  const record = action.mode === "create" ? null : action.record;
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [form, setForm] = useState({
    description: record?.description ?? "",
    amount: record?.amount.toString() ?? "",
    recurring: record?.source === "subscription",
    hasDate: record?.next_date != null || record?.source === "subscription",
    dueDate: record?.next_date ?? today(),
    category: record?.category ?? "",
    subcategory: record?.subcategory ?? "",
    notes: record?.notes ?? "",
    renewalMode: record?.renewal_mode ?? "same_day",
    renewalInterval: record?.renewal_interval?.toString() ?? "1",
  });
  const mutation = useMutation({
    mutationFn: async () => {
      const [category, subcategory] = categoryValues(
        categories.data?.支出 ?? {},
        form.category,
        form.subcategory,
      );
      if (action.mode === "confirm") {
        const payload: ConfirmExpected = {
          description: form.description.trim(),
          amount: Number(form.amount),
          payment_date: form.dueDate,
          category,
          subcategory,
          notes: form.notes.trim() || null,
        };
        return api.confirmExpected(action.record, payload, idempotencyKey);
      }
      const payload: ExpectedWrite = {
        description: form.description.trim(),
        amount: Number(form.amount),
        recurring: form.recurring,
        due_date: form.recurring || form.hasDate ? form.dueDate : null,
        category,
        subcategory,
        notes: form.notes.trim() || null,
        renewal_mode: form.renewalMode as "same_day" | "fixed_days",
        renewal_interval: Number(form.renewalInterval),
      };
      return action.mode === "create"
        ? api.createExpected(payload, idempotencyKey)
        : api.updateExpected(action.record, payload);
    },
    onSuccess: async () => {
      await invalidateFinance(queryClient);
      onDone();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };
  const isConfirm = action.mode === "confirm";
  return (
    <form className="space-y-4" onSubmit={submit}>
      <DialogHeader>
        <DialogTitle>
          {isConfirm
            ? "确认入账"
            : action.mode === "create"
              ? "新增预计支出"
              : "编辑预计支出"}
        </DialogTitle>
        <DialogDescription>
          {isConfirm
            ? "本次付款只会在确认后写入账目。"
            : "一次性计划和周期付款共用一张清单。"}
        </DialogDescription>
      </DialogHeader>
      <Field label="描述">
        <Input
          value={form.description}
          required
          onChange={(event) =>
            setForm({ ...form, description: event.target.value })
          }
        />
      </Field>
      <Field label={isConfirm ? "实际金额" : "预计金额"}>
        <Input
          type="number"
          min="0.01"
          step="0.01"
          value={form.amount}
          required
          onChange={(event) => setForm({ ...form, amount: event.target.value })}
        />
      </Field>
      {!isConfirm && action.mode === "create" && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.recurring}
            onChange={(event) =>
              setForm({
                ...form,
                recurring: event.target.checked,
                hasDate: event.target.checked || form.hasDate,
              })
            }
          />
          周期性付款
        </label>
      )}
      {!isConfirm && !form.recurring && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.hasDate}
            onChange={(event) =>
              setForm({ ...form, hasDate: event.target.checked })
            }
          />
          设置预计日期
        </label>
      )}
      {(isConfirm || form.recurring || form.hasDate) && (
        <Field
          label={
            isConfirm ? "付款日期" : form.recurring ? "付款日" : "预计日期"
          }
        >
          <Input
            type="date"
            value={form.dueDate}
            required
            onChange={(event) =>
              setForm({ ...form, dueDate: event.target.value })
            }
          />
        </Field>
      )}
      {!isConfirm && form.recurring && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="续费方式">
            <select
              className={selectClass}
              value={form.renewalMode}
              onChange={(event) =>
                setForm({
                  ...form,
                  renewalMode: event.target.value as "same_day" | "fixed_days",
                })
              }
            >
              <option value="same_day">按月同日</option>
              <option value="fixed_days">固定天数</option>
            </select>
          </Field>
          <Field
            label={form.renewalMode === "same_day" ? "间隔月数" : "间隔天数"}
          >
            <Input
              type="number"
              min="1"
              max={form.renewalMode === "same_day" ? "120" : "730"}
              value={form.renewalInterval}
              onChange={(event) =>
                setForm({ ...form, renewalInterval: event.target.value })
              }
            />
          </Field>
        </div>
      )}
      <CategoryFields
        categories={categories.data?.支出 ?? {}}
        category={form.category}
        subcategory={form.subcategory}
        onChange={(category, subcategory) =>
          setForm({ ...form, category, subcategory })
        }
      />
      <Field label="备注">
        <textarea
          className={textareaClass}
          value={form.notes}
          onChange={(event) => setForm({ ...form, notes: event.target.value })}
        />
      </Field>
      <Button
        className="w-full"
        disabled={
          mutation.isPending ||
          !form.description.trim() ||
          Number(form.amount) <= 0
        }
      >
        {mutation.isPending ? "提交中…" : isConfirm ? "确认并记账" : "保存"}
      </Button>
      <Feedback error={mutation.error} />
    </form>
  );
}

function PrepaidForm({
  action,
  onDone,
}: {
  action: PrepaidAction;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: api.categories,
  });
  const record = action.mode === "edit" ? action.record : null;
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [form, setForm] = useState({
    description: record?.description ?? "",
    amount: record?.amount.toString() ?? "",
    paymentDate: today(),
    months: record?.months.toString() ?? "12",
    startMonth: record?.start_month ?? today().slice(0, 7),
    category: record?.category ?? "",
    subcategory: record?.subcategory ?? "",
    notes: record?.notes ?? "",
  });
  const mutation = useMutation({
    mutationFn: () => {
      const [category, subcategory] = categoryValues(
        categories.data?.支出 ?? {},
        form.category,
        form.subcategory,
      );
      const base: PrepaidUpdate = {
        description: form.description.trim(),
        months: Number(form.months),
        start_month: form.startMonth,
        category,
        subcategory,
        notes: form.notes.trim() || null,
      };
      if (action.mode === "edit")
        return api.updatePrepaid(action.record.id, base);
      const payload: PrepaidWrite = {
        ...base,
        amount: Number(form.amount),
        payment_date: form.paymentDate,
      };
      return api.createPrepaid(payload, idempotencyKey);
    },
    onSuccess: async () => {
      await invalidateFinance(queryClient);
      onDone();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };
  return (
    <form className="space-y-4" onSubmit={submit}>
      <DialogHeader>
        <DialogTitle>
          {action.mode === "create" ? "新增预付摊销" : "编辑预付摊销"}
        </DialogTitle>
        <DialogDescription>
          {record
            ? `关联流水 #${record.transaction_id}；金额和付款日期请到账目页修改。`
            : "保存时会同时生成付款流水与摊销设置。"}
        </DialogDescription>
      </DialogHeader>
      <Field label="描述">
        <Input
          value={form.description}
          required
          onChange={(event) =>
            setForm({ ...form, description: event.target.value })
          }
        />
      </Field>
      {action.mode === "create" && (
        <>
          <Field label="总金额">
            <Input
              type="number"
              min="0.01"
              step="0.01"
              value={form.amount}
              required
              onChange={(event) =>
                setForm({ ...form, amount: event.target.value })
              }
            />
          </Field>
          <Field label="付款日期">
            <Input
              type="date"
              value={form.paymentDate}
              onChange={(event) =>
                setForm({ ...form, paymentDate: event.target.value })
              }
            />
          </Field>
        </>
      )}
      <div className="grid grid-cols-2 gap-3">
        <Field label="摊销月数">
          <Input
            type="number"
            min="1"
            max="120"
            value={form.months}
            onChange={(event) =>
              setForm({ ...form, months: event.target.value })
            }
          />
        </Field>
        <Field label="摊销开始月份">
          <Input
            type="month"
            value={form.startMonth}
            onChange={(event) =>
              setForm({ ...form, startMonth: event.target.value })
            }
          />
        </Field>
      </div>
      <CategoryFields
        categories={categories.data?.支出 ?? {}}
        category={form.category}
        subcategory={form.subcategory}
        onChange={(category, subcategory) =>
          setForm({ ...form, category, subcategory })
        }
      />
      <Field label="备注">
        <textarea
          className={textareaClass}
          value={form.notes}
          onChange={(event) => setForm({ ...form, notes: event.target.value })}
        />
      </Field>
      <Button
        className="w-full"
        disabled={
          mutation.isPending ||
          !form.description.trim() ||
          (action.mode === "create" && Number(form.amount) <= 0)
        }
      >
        {mutation.isPending
          ? "提交中…"
          : action.mode === "create"
            ? "保存并记账"
            : "保存修改"}
      </Button>
      <Feedback error={mutation.error} />
    </form>
  );
}

function CategoryFields({
  categories,
  category,
  subcategory,
  onChange,
}: {
  categories: Record<string, string[]>;
  category: string;
  subcategory: string;
  onChange: (category: string, subcategory: string) => void;
}) {
  const names = Object.keys(categories);
  const selected = category || names[0] || "";
  const children = categories[selected] ?? [];
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label="主类别">
        <select
          className={selectClass}
          value={selected}
          onChange={(event) =>
            onChange(
              event.target.value,
              categories[event.target.value]?.[0] ?? "",
            )
          }
        >
          {names.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </Field>
      <Field label="子类别">
        <select
          className={selectClass}
          value={
            subcategory && children.includes(subcategory)
              ? subcategory
              : (children[0] ?? "")
          }
          onChange={(event) => onChange(selected, event.target.value)}
        >
          {children.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </Field>
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
function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-lg border bg-white p-8 text-center text-neutral-500">
      {text}
    </div>
  );
}
function StateBadge({ state }: { state: string }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-1 text-xs",
        state === "已过期"
          ? "bg-red-100 text-red-700"
          : state === "今日待确认"
            ? "bg-amber-100 text-amber-800"
            : "bg-neutral-100 text-neutral-600",
      )}
    >
      {state}
    </span>
  );
}
function categoryLabel(record: {
  category?: string | null;
  subcategory?: string | null;
}) {
  return (
    [record.category, record.subcategory].filter(Boolean).join(" / ") || "—"
  );
}
function categoryValues(
  categories: Record<string, string[]>,
  category: string,
  subcategory: string,
): [string | null, string | null] {
  const selectedCategory = category || Object.keys(categories)[0] || null;
  if (!selectedCategory) return [null, null];
  const children = categories[selectedCategory] ?? [];
  return [
    selectedCategory,
    subcategory && children.includes(subcategory)
      ? subcategory
      : (children[0] ?? null),
  ];
}
function money(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
  }).format(value);
}
