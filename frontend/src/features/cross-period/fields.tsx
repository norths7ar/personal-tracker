import { cn } from "@/lib/utils";
import { Field, selectClass } from "@/features/record/entry-shared";

export function CategoryFields({
  categories,
  category,
  subcategory,
  onChange,
  preserveCurrent = false,
}: {
  preserveCurrent?: boolean;
  categories: Record<string, string[]>;
  category: string;
  subcategory: string;
  onChange: (category: string, subcategory: string) => void;
}) {
  const names = [...new Set([...Object.keys(categories), ...(category ? [category] : [])])];
  const selected = preserveCurrent ? category : category || names[0] || "";
  const children = [
    ...new Set([...(categories[selected] ?? []), ...(subcategory ? [subcategory] : [])]),
  ];
  return (
    <div className="paired-fields">
      <Field label="主类别">
        <select
          className={selectClass}
          value={selected}
          onChange={(event) =>
            onChange(event.target.value, categories[event.target.value]?.[0] ?? "")
          }
        >
          {preserveCurrent && <option value="">无</option>}
          {names.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </Field>
      <Field label="子类别">
        <select
          className={selectClass}
          value={preserveCurrent ? subcategory : subcategory || children[0] || ""}
          onChange={(event) => onChange(selected, event.target.value)}
        >
          {(preserveCurrent || !children.length) && <option value="">无</option>}
          {children.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </Field>
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <div className="empty-panel">{text}</div>;
}

export function StateBadge({ state }: { state: string }) {
  return (
    <span
      className={cn(
        "status-badge",
        state === "已过期"
          ? "status-overdue"
          : state === "今日待确认"
            ? "status-due"
            : "status-neutral",
      )}
    >
      {state}
    </span>
  );
}
