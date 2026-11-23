import { EditorFooter } from "@/components/record-actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  categoryLabel,
  money,
  type BreakdownRow,
  type DetailSelection,
  type PeriodData,
} from "./utils";

export function DetailDialog({
  data,
  selection,
  onClose,
}: {
  data: PeriodData;
  selection: DetailSelection | null;
  onClose: () => void;
}) {
  const entries = selection
    ? (data.entries ?? []).filter(
        (entry) =>
          entry.bucket === selection.bucket &&
          (entry.category || "") === (selection.row.category || "") &&
          (selection.level === "category" ||
            (entry.subcategory || "") === (selection.row.subcategory || "")),
      )
    : [];
  return (
    <Dialog
      open={Boolean(selection)}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      {selection && (
        <DialogContent layout="center" className="detail-dialog">
          <DialogHeader>
            <DialogTitle>
              {categoryLabel(selection.row)} · {money(selection.row.total)}
            </DialogTitle>
            <DialogDescription>
              本期计入金额合计来自以下记录；退款显示负数，摊销显示本期份额。
            </DialogDescription>
          </DialogHeader>
          <div className="table-scroll">
            <table className="data-table">
              <thead className="summary-table-heading">
                <tr>
                  <th className="summary-heading-cell">交易日期</th>
                  <th className="summary-heading-cell">描述</th>
                  <th className="summary-heading-cell">归属日期</th>
                  <th className="summary-heading-amount">原金额</th>
                  <th className="summary-heading-amount">本期计入</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry, index) => (
                  <tr key={`${entry.id}-${entry.allocation_date}-${index}`} className="data-row">
                    <td className="summary-date-cell">{entry.date}</td>
                    <td className="summary-description-cell">
                      {entry.description}
                      <span className="summary-entry-note">#{entry.id}</span>
                    </td>
                    <td className="summary-date-cell">{entry.allocation_date}</td>
                    <td className="summary-amount-cell">{money(entry.amount)}</td>
                    <td className="summary-total-cell">{money(entry.contribution)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <EditorFooter>
            <Button variant="outline" onClick={onClose}>
              关闭明细
            </Button>
          </EditorFooter>
        </DialogContent>
      )}
    </Dialog>
  );
}

export function Breakdown({
  title,
  rows,
  onSelect,
}: {
  title: string;
  rows: BreakdownRow[];
  onSelect: (row: BreakdownRow) => void;
}) {
  const max = Math.max(...rows.map((row) => Math.abs(row.total)), 1);
  return (
    <div className="content-panel analysis-breakdown">
      <h3 className="panel-title">{title}</h3>
      {!rows.length ? (
        <p className="empty-message">本期没有记录。</p>
      ) : (
        <table className="data-table">
          <thead className="summary-table-heading">
            <tr>
              <th className="breakdown-heading-cell">分类</th>
              <th className="breakdown-heading-amount">金额</th>
              <th className="breakdown-heading-amount">笔数</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.category}-${row.subcategory}`} className="data-row">
                <td className="breakdown-label-cell">
                  <button className="breakdown-link" onClick={() => onSelect(row)}>
                    {categoryLabel(row)}
                    <span className="visually-hidden">，查看记录</span>
                  </button>
                  <div className="breakdown-track">
                    <div
                      className="breakdown-fill"
                      style={{ width: `${(Math.abs(row.total) / max) * 100}%` }}
                    />
                  </div>
                </td>
                <td className="breakdown-amount">{money(row.total)}</td>
                <td className="breakdown-count">{row.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
