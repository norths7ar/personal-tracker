import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { api, type PrepaidRecord } from "@/api/client";
import { invalidateFinance } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { Feedback } from "@/features/record/entry-shared";
import { categoryLabel, money, type PrepaidAction } from "./utils";
import { Empty } from "./fields";

export function PrepaidTable({
  records,
  onAction,
}: {
  records: PrepaidRecord[];
  onAction: (action: PrepaidAction) => void;
}) {
  const queryClient = useQueryClient();
  const deletion = useMutation({
    mutationFn: api.deletePrepaid,
    onSuccess: () => invalidateFinance(queryClient),
  });
  if (!records.length) return <Empty text="暂无预付摊销。" />;
  return (
    <div className="table-panel-scroll">
      <table className="prepaid-table">
        <thead className="data-table-heading">
          <tr>
            <th className="data-cell">描述</th>
            <th className="data-cell">总金额</th>
            <th className="data-cell">月均</th>
            <th className="data-cell">剩余月数</th>
            <th className="data-cell">摊销开始</th>
            <th className="data-cell">分类</th>
            <th className="data-cell-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr className="data-row" key={record.id}>
              <td className="data-cell-title">{record.description}</td>
              <td className="data-cell">{money(record.amount)}</td>
              <td className="data-cell">{money(record.monthly_equivalent)}</td>
              <td className="data-cell">{record.remaining_months}</td>
              <td className="data-cell">{record.start_month}</td>
              <td className="data-cell">{categoryLabel(record)}</td>
              <td className="data-cell">
                <div className="row-actions">
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
                    aria-label={`删除摊销 ${record.description}`}
                    disabled={deletion.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          `确认删除“${record.description}”的摊销设置？关联流水不会删除。`,
                        )
                      )
                        deletion.mutate(record.id);
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
      <Feedback error={deletion.error} />
    </div>
  );
}
