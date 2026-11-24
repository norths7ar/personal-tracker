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
  const entries = selection ? detailEntries(data, selection) : [];
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
              每笔交易只列一行；退款显示负数，有生效期的支出显示本期分摊金额。
            </DialogDescription>
          </DialogHeader>
          <div className="table-scroll">
            <table className="data-table">
              <thead className="summary-table-heading">
                <tr>
                  <th className="summary-heading-cell">交易日期</th>
                  <th className="summary-heading-cell">描述</th>
                  <th className="summary-heading-cell">本期归属日期</th>
                  <th className="summary-heading-amount">原金额</th>
                  <th className="summary-heading-amount">本期计入</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id} className="data-row">
                    <td className="summary-date-cell">{entry.date}</td>
                    <td className="summary-description-cell">
                      {entry.description}
                      <span className="summary-entry-note">#{entry.id}</span>
                    </td>
                    <td className="summary-date-cell">
                      {entry.firstDate === entry.lastDate
                        ? entry.firstDate
                        : `${entry.firstDate} 至 ${entry.lastDate}`}
                    </td>
                    <td className="summary-amount-cell">{money(entry.amount)}</td>
                    <td className="summary-total-cell">{money(entry.contributionCents / 100)}</td>
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

type DetailEntry = {
  id: number;
  date: string;
  description: string;
  amount: number;
  firstDate: string;
  lastDate: string;
  contributionCents: number;
};

function detailEntries(data: PeriodData, selection: DetailSelection) {
  const grouped = new Map<number, DetailEntry>();
  for (const entry of data.entries ?? []) {
    if (entry.bucket !== selection.bucket) continue;
    if ((entry.category || "") !== (selection.row.category || "")) continue;
    if (
      selection.level === "subcategory" &&
      (entry.subcategory || "") !== (selection.row.subcategory || "")
    )
      continue;

    const cents = Math.round(entry.contribution * 100);
    const group = grouped.get(entry.id);
    if (group) {
      group.contributionCents += cents;
      if (entry.allocation_date < group.firstDate) group.firstDate = entry.allocation_date;
      if (entry.allocation_date > group.lastDate) group.lastDate = entry.allocation_date;
    } else {
      grouped.set(entry.id, {
        id: entry.id,
        date: entry.date,
        description: entry.description,
        amount: entry.amount,
        firstDate: entry.allocation_date,
        lastDate: entry.allocation_date,
        contributionCents: cents,
      });
    }
  }
  return [...grouped.values()];
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
