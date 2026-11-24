import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Trash2 } from "lucide-react";
import { api, type ExpectedRecord } from "@/api/client";
import { invalidateFinance } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { Feedback } from "@/features/record/entry-shared";
import { formatMoney } from "../utils";
import { categoryLabel, coverageDurationLabel, type ExpectedAction } from "./utils";
import { StateBadge } from "./fields";

export function ExpectedTable({
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
  if (!records.length) return <div className="empty-panel">暂无付款计划。</div>;
  return (
    <div className="table-panel">
      <div className="table-scroll">
        <table className="data-table expected-table">
          <thead className="data-table-heading">
            <tr>
              <th className="data-cell">描述</th>
              <th className="data-cell expected-amount">金额</th>
              <th className="data-cell">付款日</th>
              <th className="data-cell">周期</th>
              <th className="data-cell">生效期</th>
              <th className="data-cell">分类</th>
              <th className="data-cell">状态</th>
              <th className="data-cell expected-actions-heading">操作</th>
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr className="data-row" key={`${record.source}-${record.id}`}>
                <td className="data-cell expected-title">{record.description}</td>
                <td className="data-cell expected-amount">{formatMoney(record.amount)}</td>
                <td className="data-cell expected-date">{record.next_date || "—"}</td>
                <td className="data-cell">{record.cycle}</td>
                <td className="data-cell">{coverageDurationLabel(record) || "—"}</td>
                <td className="data-cell">{categoryLabel(record)}</td>
                <td className="data-cell">
                  <StateBadge state={record.state} />
                </td>
                <td className="data-cell">
                  <div className="expected-actions">
                    <Button size="sm" onClick={() => onAction({ mode: "confirm", record })}>
                      <Check size={14} />
                      入账
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`编辑 ${record.description}`}
                      onClick={() => onAction({ mode: "edit", record })}
                    >
                      <Pencil size={15} />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`删除 ${record.description}`}
                      disabled={deletion.isPending}
                      onClick={() => {
                        if (window.confirm(`确认删除“${record.description}”？历史流水不会受影响。`))
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
      </div>
      <Feedback error={deletion.error} />
    </div>
  );
}
