import { CalendarDays } from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ComponentPropsWithRef,
} from "react";

import { cn } from "@/lib/utils";

function dateError(
  value: string,
  min?: string | number,
  max?: string | number,
): string {
  if (!value) return "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value))
    return "请输入完整日期，格式为 YYYY-MM-DD";
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  const date = new Date(`${value}T00:00:00`);
  if (
    year < 1 ||
    date.getFullYear() !== year ||
    date.getMonth() + 1 !== month ||
    date.getDate() !== day
  ) {
    return "请输入有效日期";
  }
  if (min && value < String(min)) return `日期不能早于 ${min}`;
  if (max && value > String(max)) return `日期不能晚于 ${max}`;
  return "";
}

export function DateInput({
  className,
  value,
  defaultValue,
  onChange,
  onBlur,
  ref,
  min,
  max,
  disabled,
  readOnly,
  placeholder = "选择日期",
  resetKey,
  ...props
}: ComponentPropsWithRef<"input"> & { resetKey?: string | number }) {
  const controlled = value === undefined ? undefined : String(value);
  const [previousValue, setPreviousValue] = useState(controlled);
  const [previousResetKey, setPreviousResetKey] = useState(resetKey);
  const [draft, setDraft] = useState(controlled ?? String(defaultValue ?? ""));
  const [blurred, setBlurred] = useState(false);
  const textRef = useRef<HTMLInputElement | null>(null);
  const pickerRef = useRef<HTMLInputElement | null>(null);
  const errorId = useId();
  // External resets and record changes replace the draft; incomplete typing stays local.
  if (controlled !== previousValue || resetKey !== previousResetKey) {
    setPreviousValue(controlled);
    setPreviousResetKey(resetKey);
    setDraft(controlled ?? String(defaultValue ?? ""));
    setBlurred(false);
  }
  const error = dateError(draft, min, max);
  const attachRef = useCallback(
    (node: HTMLInputElement | null) => {
      textRef.current = node;
      if (typeof ref === "function") return ref(node);
      if (ref) ref.current = node;
    },
    [ref],
  );
  useEffect(() => {
    textRef.current?.setCustomValidity(error);
  }, [error]);

  return (
    <span className="relative block">
      <input
        {...props}
        ref={attachRef}
        type="text"
        value={draft}
        disabled={disabled}
        readOnly={readOnly}
        placeholder={placeholder}
        title="输入日期（YYYY-MM-DD）或使用右侧日历选择"
        className={cn(
          "h-9 w-full rounded-md border border-neutral-300 bg-white px-3 pr-10 text-sm outline-none placeholder:text-neutral-400 focus:border-neutral-500 focus:ring-2 focus:ring-neutral-200 disabled:opacity-50",
          className,
        )}
        aria-invalid={error ? true : props["aria-invalid"]}
        aria-describedby={
          [props["aria-describedby"], error && blurred ? errorId : ""]
            .filter(Boolean)
            .join(" ") || undefined
        }
        onChange={(event) => {
          const next = event.target.value;
          setDraft(next);
          setBlurred(false);
          event.target.setCustomValidity(dateError(next, min, max));
          if (!dateError(next, min, max)) onChange?.(event);
        }}
        onBlur={(event) => {
          setBlurred(true);
          onBlur?.(event);
        }}
      />
      <button
        type="button"
        aria-label="打开日历选择日期"
        disabled={disabled || readOnly}
        className="absolute right-1 top-1 flex h-7 w-7 items-center justify-center rounded text-neutral-500 hover:bg-neutral-100 focus-visible:outline-2 focus-visible:outline-neutral-500 disabled:opacity-50"
        onClick={() => {
          const picker = pickerRef.current;
          if (!picker) return;
          if (typeof picker.showPicker === "function") picker.showPicker();
          else picker.click();
        }}
      >
        <CalendarDays className="h-4 w-4" />
      </button>
      <input
        ref={pickerRef}
        type="date"
        tabIndex={-1}
        aria-hidden="true"
        className="pointer-events-none absolute right-1 top-1 h-7 w-7 opacity-0"
        value={dateError(draft) ? "" : draft}
        min={min}
        max={max}
        disabled={disabled || readOnly}
        onChange={(event) => {
          const next = event.target.value;
          const input = textRef.current;
          if (!input || dateError(next, min, max)) return;
          setDraft(next);
          setBlurred(false);
          input.value = next;
          input.setCustomValidity("");
          onChange?.({ ...event, target: input, currentTarget: input });
          input.focus();
        }}
      />
      {error && blurred && (
        <span id={errorId} className="mt-1 block text-xs text-red-600">
          {error}
        </span>
      )}
    </span>
  );
}
