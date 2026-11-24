import { Feedback } from "@/features/record/entry-shared";
import { CaptureRow } from "./capture-row";
import { LedgerPending } from "./ledger-pending";
import { useCapturePending } from "./use-capture-pending";
import "./pending-page.css";

export function PendingPage() {
  const pending = useCapturePending();
  return (
    <section className="page-stack pending-page">
      <header className="page-heading">
        <h1 className="page-title">待处理</h1>
        {pending.data && <span className="pending-count">{pending.data.pending_count} 项</span>}
      </header>
      <section className="page-stack" aria-labelledby="capture-review-title">
        <div className="page-heading">
          <h2 id="capture-review-title" className="section-title">
            收集记录
          </h2>
          {Boolean(pending.data?.processing_count) && (
            <span className="help-text">{pending.data?.processing_count} 项正在后台整理</span>
          )}
        </div>
        <p className="help-text">高置信度记录已自动入账，这里只保留正在整理和需要你确认的内容。</p>
        {pending.isPending ? (
          <p role="status">正在读取…</p>
        ) : pending.isError ? (
          <Feedback error={pending.error} />
        ) : pending.data.items.length ? (
          <div className="capture-queue">
            {pending.data.items.map((item) => (
              <CaptureRow key={item.id} item={item} />
            ))}
          </div>
        ) : (
          <p className="muted-text">没有需要审阅的收集记录。</p>
        )}
      </section>
      <LedgerPending />
    </section>
  );
}
