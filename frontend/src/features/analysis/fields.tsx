import { cn } from "@/lib/utils";

export function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="metric-panel">
      <p className="muted-text">{label}</p>
      <p className="metric-value">{value}</p>
      {hint && <p className="metric-hint">{hint}</p>}
    </div>
  );
}

export function Segmented({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="segmented-control">
      {options.map((option) => (
        <button
          key={option.value}
          aria-pressed={value === option.value}
          className={cn("segmented-option", value === option.value && "segmented-selected")}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
