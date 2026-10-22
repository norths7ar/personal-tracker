import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import { api, type Todo, type TodoWrite } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { textareaClass } from "@/pages/record/entry-shared";

export function TodoPage() {
  const queryClient = useQueryClient();
  const todos = useQuery({ queryKey: ["todos"], queryFn: api.todos });
  const [editor, setEditor] = useState<Todo | "new" | null>(null);
  const [completedOpen, setCompletedOpen] = useState(false);
  const locked = useRef(false);
  const action = useMutation({
    mutationFn: (work: () => Promise<unknown>) => work(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["todos"] });
    },
  });
  const run = async (work: () => Promise<unknown>) => {
    if (locked.current) return;
    locked.current = true;
    try {
      await action.mutateAsync(work);
    } catch {
      /* The mutation error is shown below. */
    } finally {
      locked.current = false;
    }
  };
  const records = todos.data ?? [];
  const active = records.find((todo) => todo.status === "active");
  const pending = records.filter((todo) => todo.status === "pending");
  const completed = records.filter((todo) => todo.status === "completed");
  const busy = action.isPending;
  const changeState = (todo: Todo, status: Todo["status"]) =>
    run(() => api.setTodoState(todo.id, { status }));
  const remove = (todo: Todo) => {
    if (window.confirm(`删除「${todo.title}」？此操作无法撤销。`))
      void run(() => api.deleteTodo(todo.id));
  };
  const secondaryActions = (todo: Todo) => (
    <>
      <Button
        variant="ghost"
        size="icon"
        disabled={busy}
        aria-label={`编辑 ${todo.title}`}
        title="编辑"
        onClick={() => {
          action.reset();
          setEditor(todo);
        }}
      >
        <Pencil size={15} />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        disabled={busy}
        aria-label={`删除 ${todo.title}`}
        title="删除"
        onClick={() => remove(todo)}
      >
        <Trash2 size={15} />
      </Button>
    </>
  );

  return (
    <section className="mx-auto max-w-4xl space-y-7">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            待办
          </h1>
          <p className="mt-1 text-sm text-neutral-500">
            记下想做的事，选一件开始。
          </p>
        </div>
        <Button
          disabled={busy}
          onClick={() => {
            action.reset();
            setEditor("new");
          }}
        >
          <Plus size={16} />
          添加待办
        </Button>
      </header>

      {action.isError && editor === null && (
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          {action.error.message}
        </p>
      )}
      {todos.isPending ? (
        <p className="py-12 text-center text-sm text-neutral-500">
          正在读取待办…
        </p>
      ) : todos.isError ? (
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-white p-6"
        >
          <p className="mb-3 text-sm text-red-700">
            读取失败：{todos.error.message}
          </p>
          <Button variant="outline" onClick={() => void todos.refetch()}>
            重新读取
          </Button>
        </div>
      ) : (
        <>
          <section
            aria-label="当前任务"
            className="overflow-hidden rounded-2xl border border-stone-300 bg-stone-100/80 p-6 sm:p-8"
          >
            <div className="mb-5 flex items-center gap-2 text-xs font-medium tracking-wider text-stone-600">
              <span
                className={`size-2 rounded-full ${active ? "bg-stone-700" : "bg-stone-300"}`}
              />
              {active ? "现在做这件" : "从一件事开始"}
            </div>
            {active ? (
              <>
                <h2 className="break-words text-xl font-semibold leading-relaxed sm:text-2xl">
                  {active.title}
                </h2>
                {active.notes && (
                  <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-7 text-neutral-600">
                    {active.notes}
                  </p>
                )}
                <div className="mt-7 flex flex-wrap items-center gap-2">
                  <Button
                    disabled={busy}
                    onClick={() => void changeState(active, "completed")}
                  >
                    <Check size={16} />
                    完成
                  </Button>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => void changeState(active, "pending")}
                  >
                    放回待做
                  </Button>
                  <div className="ml-auto flex text-neutral-500">
                    {secondaryActions(active)}
                  </div>
                </div>
              </>
            ) : (
              <>
                <h2 className="text-xl font-medium">
                  {pending.length
                    ? "选好一件，就可以开始了。"
                    : "有什么想推进的事？"}
                </h2>
                <p className="mt-2 text-sm leading-6 text-neutral-500">
                  {pending.length
                    ? "从下面的待做中选择，不必一次安排好所有事情。"
                    : "先记下来，不用分类，也不用定一个期限。"}
                </p>
                {!pending.length && (
                  <Button
                    className="mt-5"
                    variant="outline"
                    onClick={() => setEditor("new")}
                  >
                    <Plus size={16} />
                    记一件事
                  </Button>
                )}
              </>
            )}
          </section>

          <section aria-labelledby="pending-title">
            <div className="mb-3 flex items-center gap-2">
              <h2 id="pending-title" className="text-sm font-semibold">
                待做
              </h2>
              <span className="text-xs text-neutral-400">{pending.length}</span>
              {active && pending.length > 0 && (
                <span className="ml-auto text-xs text-neutral-500">
                  开始另一件，当前任务会放回待做
                </span>
              )}
            </div>
            <div className="divide-y divide-neutral-100 overflow-hidden rounded-xl border border-neutral-200 bg-white">
              {pending.length ? (
                pending.map((todo, index) => (
                  <article key={todo.id} className="p-4 sm:p-5">
                    <div className="min-w-0">
                      <h3 className="break-words font-medium leading-6">
                        {todo.title}
                      </h3>
                      {todo.notes && (
                        <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-neutral-500">
                          {todo.notes}
                        </p>
                      )}
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-1">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy}
                        onClick={() => void changeState(todo, "active")}
                      >
                        <Play size={13} />
                        {active ? "换做这件" : "开始"}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => void changeState(todo, "completed")}
                      >
                        <Check size={14} />
                        完成
                      </Button>
                      <div className="ml-auto flex text-neutral-400">
                        <Button
                          size="icon"
                          variant="ghost"
                          disabled={busy || index === 0}
                          aria-label={`上移 ${todo.title}`}
                          title="上移"
                          onClick={() =>
                            void run(() =>
                              api.moveTodo(todo.id, { direction: "up" }),
                            )
                          }
                        >
                          <ArrowUp size={15} />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          disabled={busy || index === pending.length - 1}
                          aria-label={`下移 ${todo.title}`}
                          title="下移"
                          onClick={() =>
                            void run(() =>
                              api.moveTodo(todo.id, { direction: "down" }),
                            )
                          }
                        >
                          <ArrowDown size={15} />
                        </Button>
                        {secondaryActions(todo)}
                      </div>
                    </div>
                  </article>
                ))
              ) : (
                <p className="p-6 text-sm text-neutral-400">
                  {active
                    ? "没有其他待做，先做眼前这一件。"
                    : "这里还没有待做的事。"}
                </p>
              )}
            </div>
          </section>

          {completed.length > 0 && (
            <section>
              <button
                type="button"
                aria-expanded={completedOpen}
                aria-controls="completed-todos"
                onClick={() => setCompletedOpen(!completedOpen)}
                className="flex w-full items-center gap-2 rounded-md py-2 text-sm text-neutral-500 hover:text-neutral-900"
              >
                <ChevronDown
                  size={16}
                  className={`transition-transform ${completedOpen ? "" : "-rotate-90"}`}
                />
                已完成
                <span className="text-xs text-neutral-400">
                  {completed.length}
                </span>
              </button>
              {completedOpen && (
                <div
                  id="completed-todos"
                  className="mt-2 divide-y divide-neutral-200"
                >
                  {completed.map((todo) => (
                    <article
                      key={todo.id}
                      className="flex flex-wrap items-center gap-3 py-3"
                    >
                      <Check size={15} className="shrink-0 text-neutral-400" />
                      <p className="min-w-0 flex-1 break-words text-sm text-neutral-500">
                        {todo.title}
                      </p>
                      <div className="flex items-center text-neutral-400">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy}
                          onClick={() => void changeState(todo, "pending")}
                        >
                          <RotateCcw size={14} />
                          恢复
                        </Button>
                        {secondaryActions(todo)}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}

      <Dialog
        open={editor !== null}
        onOpenChange={(open) => {
          if (!open && !busy) setEditor(null);
        }}
      >
        <DialogContent layout="center" className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editor === "new" ? "添加待办" : "编辑待办"}
            </DialogTitle>
            <DialogDescription>写下想做的事，说明可以留空。</DialogDescription>
          </DialogHeader>
          {editor !== null && (
            <TodoForm
              key={editor === "new" ? "new" : editor.id}
              todo={editor === "new" ? undefined : editor}
              busy={busy}
              error={action.error}
              onCancel={() => setEditor(null)}
              onSave={(entry) =>
                void run(async () => {
                  if (editor === "new") await api.createTodo(entry);
                  else await api.updateTodo(editor.id, entry);
                  setEditor(null);
                })
              }
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function TodoForm({
  todo,
  busy,
  error,
  onSave,
  onCancel,
}: {
  todo?: Todo;
  busy: boolean;
  error: Error | null;
  onSave: (entry: TodoWrite) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(todo?.title ?? "");
  const [notes, setNotes] = useState(todo?.notes ?? "");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (title.trim() && !busy)
      onSave({ title: title.trim(), notes: notes.trim() });
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <label className="block space-y-2 text-sm">
        <span>想做什么</span>
        <Input
          autoFocus
          required
          maxLength={200}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="例如：完成项目的导入功能"
          disabled={busy}
        />
      </label>
      <label className="block space-y-2 text-sm">
        <span>
          补充说明 <span className="text-neutral-400">（可选）</span>
        </span>
        <textarea
          className={`${textareaClass} min-h-28`}
          maxLength={5000}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="需要时，留一点上下文。"
          disabled={busy}
        />
      </label>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error.message}
        </p>
      )}
      <div className="flex justify-end gap-2 pt-2">
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={onCancel}
        >
          取消
        </Button>
        <Button type="submit" disabled={busy || !title.trim()}>
          {busy ? "正在保存…" : todo ? "保存" : "添加"}
        </Button>
      </div>
    </form>
  );
}
