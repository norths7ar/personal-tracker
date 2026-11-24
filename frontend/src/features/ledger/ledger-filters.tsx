import { Checkbox } from "@radix-ui/themes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FilterSelect } from "./fields";
import { transactionTypes } from "./utils";
import type { useLedgerFilters } from "./use-ledger-filters";
export function LedgerFilters({ filters }: { filters: ReturnType<typeof useLedgerFilters> }) {
  const {
    categoryFilter,
    subcategoryFilter,
    typeFilter,
    startDate,
    endDate,
    coveredOnly,
    categoryOptions,
    subcategoryOptions,
    searchInput,
    searchDraft,
    setSearchDraft,
    composingRef,
    updateFilters,
    dateResetKey,
    invalidRange,
    selectMonth,
  } = filters;
  return (
    <div className="ledger-filters">
      <div className="ledger-filter-fields">
        <FilterSelect
          label="类型"
          value={typeFilter}
          options={[...transactionTypes]}
          onChange={(value) => {
            updateFilters({ type: value, category: "", subcategory: "" });
          }}
        />
        <FilterSelect
          label="主类别"
          value={categoryFilter}
          options={categoryOptions}
          onChange={(value) => {
            updateFilters({ category: value, subcategory: "" });
          }}
        />
        <FilterSelect
          label="子类别"
          value={subcategoryFilter}
          options={subcategoryOptions}
          onChange={(value) => updateFilters({ subcategory: value })}
        />
        <label className="filter-field">
          <span>搜索</span>
          <Input
            ref={searchInput}
            value={searchDraft}
            onCompositionStart={() => {
              composingRef.current = true;
            }}
            onCompositionEnd={(event) => {
              composingRef.current = false;
              setSearchDraft(event.currentTarget.value);
              updateFilters({ q: event.currentTarget.value });
            }}
            onChange={(event) => {
              setSearchDraft(event.target.value);
              if (!composingRef.current) updateFilters({ q: event.target.value });
            }}
            placeholder="搜索描述、分类或备注"
          />
        </label>
      </div>
      <div className="ledger-date-filters">
        <label className="date-filter-field">
          <span>开始日期</span>
          <Input
            type="date"
            resetKey={dateResetKey}
            value={startDate}
            max={endDate || undefined}
            onChange={(event) => updateFilters({ from: event.target.value })}
          />
        </label>
        <label className="date-filter-field">
          <span>结束日期</span>
          <Input
            type="date"
            resetKey={dateResetKey}
            value={endDate}
            min={startDate || undefined}
            onChange={(event) => updateFilters({ to: event.target.value })}
          />
        </label>
        <div className="date-shortcuts">
          <Button variant="outline" onClick={() => selectMonth(0)}>
            本月
          </Button>
          <Button variant="outline" onClick={() => selectMonth(-1)}>
            上月
          </Button>
          <Button variant="outline" onClick={() => updateFilters({ from: "", to: "" })}>
            全部日期
          </Button>
          <label className="ledger-coverage-filter">
            <Checkbox
              checked={coveredOnly}
              onCheckedChange={(checked) => updateFilters({ covered: checked === true ? "1" : "" })}
            />
            只看有生效期
          </label>
          <Button
            className="filter-reset"
            variant="ghost"
            onClick={() =>
              updateFilters({
                type: "",
                category: "",
                subcategory: "",
                q: "",
                from: "",
                to: "",
                covered: "",
              })
            }
          >
            重置筛选
          </Button>
        </div>
      </div>
      {invalidRange && (
        <p role="alert" className="filter-error">
          开始日期不能晚于结束日期。
        </p>
      )}
    </div>
  );
}
