import type { ExpectedWrite } from "@/api/client";
import { Input } from "@/components/ui/input";
import { FormField } from "./fields";
import { selectClass } from "./utils";

export type CoverageUnit = NonNullable<ExpectedWrite["coverage_unit"]>;

export function CoverageDurationFields({
  unit,
  interval,
  onChange,
}: {
  unit: CoverageUnit | "";
  interval: string;
  onChange: (unit: CoverageUnit | "", interval: string) => void;
}) {
  return (
    <div className="form-stack">
      <div className="paired-fields">
        <FormField label="生效期">
          <select
            className={selectClass}
            value={unit}
            onChange={(event) => onChange(event.target.value as CoverageUnit | "", interval)}
          >
            <option value="">不设置</option>
            <option value="months">按月</option>
            <option value="days">按天</option>
          </select>
        </FormField>
        {unit && (
          <FormField label={unit === "months" ? "生效月数" : "生效天数"}>
            <Input
              type="number"
              min="1"
              step="1"
              required
              value={interval}
              onChange={(event) => onChange(unit, event.target.value)}
            />
          </FormField>
        )}
      </div>
    </div>
  );
}
