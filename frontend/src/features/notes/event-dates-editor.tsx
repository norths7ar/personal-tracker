import { Badge, Button, Text } from "@radix-ui/themes";
import { Plus, X } from "lucide-react";
import { useState } from "react";
import { formatEventRange, type EventDateRange } from "@/api/notes";
import { DateInput } from "@/components/ui/date-input";

export function EventDatesEditor({
  value,
  onChange,
  disabled,
}: {
  value: EventDateRange[];
  onChange: (next: EventDateRange[]) => void;
  disabled?: boolean;
}) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<string | null>(null);

  function addRange() {
    if (!start) {
      setError("请先选择事件开始日期");
      return;
    }
    const resolvedEnd = end || start;
    if (start > resolvedEnd) {
      setError("结束日期不能早于开始日期");
      return;
    }
    const exists = value.some((item) => item.start_date === start && item.end_date === resolvedEnd);
    if (!exists) {
      const next = [...value, { start_date: start, end_date: resolvedEnd }].sort((a, b) =>
        a.start_date === b.start_date
          ? a.end_date.localeCompare(b.end_date)
          : a.start_date.localeCompare(b.start_date),
      );
      onChange(next);
    }
    setStart("");
    setEnd("");
    setError(null);
  }

  return (
    <div className="notes-field">
      <Text size="2" weight="medium">
        事件日期（可选，支持单天、区间及多选）
      </Text>
      {!!value.length && (
        <div className="notes-date-pills">
          {value.map((item) => {
            const key = `${item.start_date}:${item.end_date}`;
            return (
              <Badge key={key} color="gray" size="2" className="notes-date-pill">
                <span>{formatEventRange(item)}</span>
                <button
                  type="button"
                  className="notes-pill-remove"
                  disabled={disabled}
                  aria-label={`移除 ${formatEventRange(item)}`}
                  onClick={() =>
                    onChange(
                      value.filter(
                        (entry) =>
                          !(
                            entry.start_date === item.start_date && entry.end_date === item.end_date
                          ),
                      ),
                    )
                  }
                >
                  <X size={12} />
                </button>
              </Badge>
            );
          })}
        </div>
      )}
      <div className="notes-date-adder">
        <div className="notes-date-input">
          <DateInput
            aria-label="事件开始日期"
            disabled={disabled}
            value={start}
            onChange={(event) => {
              setStart(event.target.value);
              setError(null);
            }}
          />
        </div>
        <Text size="2" color="gray">
          至
        </Text>
        <div className="notes-date-input">
          <DateInput
            aria-label="事件结束日期（可选）"
            disabled={disabled}
            value={end}
            onChange={(event) => {
              setEnd(event.target.value);
              setError(null);
            }}
          />
        </div>
        <Button
          type="button"
          size="2"
          variant="soft"
          disabled={disabled || !start}
          onClick={addRange}
        >
          <Plus size={14} /> 添加
        </Button>
      </div>
      {error && (
        <Text as="p" size="2" color="red" role="alert">
          {error}
        </Text>
      )}
    </div>
  );
}
