import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "./fields";
import "./coverage-fields.css";

const shortcuts = [
  [1, "+1个月"],
  [3, "+3个月"],
  [12, "+1年"],
] as const;

function monthRange(anchor: string, months: number, nextCalendarMonth = false) {
  const start = new Date(`${anchor}T00:00:00Z`);
  if (Number.isNaN(start.getTime())) return null;
  if (nextCalendarMonth) start.setUTCMonth(start.getUTCMonth() + 1, 1);

  const end = new Date(start);
  end.setUTCMonth(end.getUTCMonth() + months + 1, 0);
  const nextCycleDay = Math.min(start.getUTCDate(), end.getUTCDate());
  end.setUTCDate(nextCycleDay - 1);

  if (start.getUTCFullYear() > 9999 || end.getUTCFullYear() > 9999) return null;
  return [start.toISOString().slice(0, 10), end.toISOString().slice(0, 10)] as const;
}

export function CoverageFields({
  start,
  end,
  paymentDate,
  onChange,
}: {
  start: string;
  end: string;
  paymentDate: string;
  onChange: (start: string, end: string) => void;
}) {
  const [resetKey, setResetKey] = useState(0);
  const replaceDates = (nextStart: string, nextEnd: string) => {
    onChange(nextStart, nextEnd);
    setResetKey((key) => key + 1);
  };
  return (
    <details
      className="manual-options"
      open={Boolean(start || end) || undefined}
      onInvalid={(event) => {
        event.currentTarget.open = true;
        const outer = event.currentTarget.parentElement?.closest("details");
        if (outer) outer.open = true;
      }}
    >
      <summary>{start && end ? `生效期（${start} 至 ${end}）` : "生效期"}</summary>
      <div className="form-stack">
        <div className="paired-fields">
          <FormField label="生效开始">
            <Input
              type="date"
              resetKey={resetKey}
              value={start}
              required={Boolean(end)}
              onChange={(event) => onChange(event.target.value, end)}
            />
          </FormField>
          <FormField label="生效结束">
            <Input
              type="date"
              resetKey={resetKey}
              value={end}
              required={Boolean(start)}
              min={start || undefined}
              onChange={(event) => onChange(start, event.target.value)}
            />
          </FormField>
        </div>
        <div className="coverage-shortcuts">
          {shortcuts.map(([months, label]) => {
            const range = monthRange(start || paymentDate, months);
            return (
              <Button
                type="button"
                size="sm"
                variant="outline"
                key={months}
                disabled={!range}
                onClick={() => range && replaceDates(...range)}
              >
                {label}
              </Button>
            );
          })}
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!monthRange(paymentDate, 1, true)}
            onClick={() => {
              const range = monthRange(paymentDate, 1, true);
              if (range) replaceDates(...range);
            }}
          >
            下个自然月
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => replaceDates("", "")}>
            清除
          </Button>
        </div>
      </div>
    </details>
  );
}
