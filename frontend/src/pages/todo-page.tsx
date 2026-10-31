import { TextArea } from "@radix-ui/themes";

import "@/styles/todo-page.css";
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
    <section className="todo-page">
      <header className="todo-heading">
        <div>
          <h1 className="page-title">待办</h1>
          <p className="page-description">记下想做的事，选一件开始。</p>
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
        <p role="alert" className="todo-action-error">
          {action.error.message}
        </p>
      )}
      {todos.isPending ? (
        <p className="loading-message">正在读取待办…</p>
      ) : todos.isError ? (
        <div role="alert" className="todo-load-error">
          <p className="todo-load-error-text">读取失败：{todos.error.message}</p>
          <Button variant="outline" onClick={() => void todos.refetch()}>
            重新读取
          </Button>
        </div>
      ) : (
        <>
          <section aria-label="当前任务" className="todo-focus">
            <div className="todo-focus-label">
              <span
                className={`todo-indicator ${active ? "todo-active-indicator" : "todo-idle-indicator"}`}
              />
              {active ? "现在做这件" : "从一件事开始"}
            </div>
            {active ? (
              <>
                <h2 className="todo-focus-title">{active.title}</h2>
                {active.notes && <p className="todo-focus-notes">{active.notes}</p>}
                <div className="todo-focus-actions">
                  <Button disabled={busy} onClick={() => void changeState(active, "completed")}>
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
                  <div className="todo-secondary-actions">{secondaryActions(active)}</div>
                </div>
              </>
            ) : (
              <>
                <h2 className="todo-empty-title">
                  {pending.length ? "选好一件，就可以开始了。" : "有什么想推进的事？"}
                </h2>
                <p className="todo-empty-description">
                  {pending.length
                    ? "从下面的待做中选择，不必一次安排好所有事情。"
                    : "先记下来，不用分类，也不用定一个期限。"}
                </p>
                {!pending.length && (
                  <Button
                    className="todo-empty-action"
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
            <div className="todo-list-heading">
              <h2 id="pending-title" className="todo-list-title">
                待做
              </h2>
              <span className="todo-count">{pending.length}</span>
              {active && pending.length > 0 && (
                <span className="todo-switch-hint">开始另一件，当前任务会放回待做</span>
              )}
            </div>
            <div className="todo-list">
              {pending.length ? (
                pending.map((todo, index) => (
                  <article key={todo.id} className="todo-item">
                    <div className="todo-item-content">
                      <h3 className="todo-item-title">{todo.title}</h3>
                      {todo.notes && <p className="todo-item-notes">{todo.notes}</p>}
                    </div>
                    <div className="todo-item-actions">
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
                      <div className="todo-order-actions">
                        <Button
                          size="icon"
                          variant="ghost"
                          disabled={busy || index === 0}
                          aria-label={`上移 ${todo.title}`}
                          title="上移"
                          onClick={() => void run(() => api.moveTodo(todo.id, { direction: "up" }))}
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
                            void run(() => api.moveTodo(todo.id, { direction: "down" }))
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
                <p className="todo-list-empty">
                  {active ? "没有其他待做，先做眼前这一件。" : "这里还没有待做的事。"}
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
                className="todo-completed-toggle"
              >
                <ChevronDown
                  size={16}
                  className={`todo-disclosure-icon ${completedOpen ? "" : "todo-disclosure-collapsed"}`}
                />
                已完成
                <span className="todo-count">{completed.length}</span>
              </button>
              {completedOpen && (
                <div id="completed-todos" className="todo-completed-list">
                  {completed.map((todo) => (
                    <article key={todo.id} className="todo-completed-item">
                      <Check size={15} className="todo-completed-icon" />
                      <p className="todo-completed-title">{todo.title}</p>
                      <div className="todo-completed-actions">
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
        <DialogContent layout="center" className="todo-dialog">
          <DialogHeader>
            <DialogTitle>{editor === "new" ? "添加待办" : "编辑待办"}</DialogTitle>
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
    if (title.trim() && !busy) onSave({ title: title.trim(), notes: notes.trim() });
  };
  return (
    <form onSubmit={submit} className="form-stack">
      <label className="todo-form-field">
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
      <label className="todo-form-field">
        <span>
          补充说明 <span className="optional-label">（可选）</span>
        </span>
        <TextArea
          className={`${textareaClass} todo-notes-input`}
          maxLength={5000}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="需要时，留一点上下文。"
          disabled={busy}
        />
      </label>
      {error && (
        <p role="alert" className="error-text">
          {error.message}
        </p>
      )}
      <div className="form-actions">
        <Button type="button" variant="outline" disabled={busy} onClick={onCancel}>
          取消
        </Button>
        <Button type="submit" disabled={busy || !title.trim()}>
          {busy ? "正在保存…" : todo ? "保存" : "添加"}
        </Button>
      </div>
    </form>
  );
}
