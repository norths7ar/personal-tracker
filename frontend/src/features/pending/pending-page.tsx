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
          <div className="pending-meta">
            {Boolean(pending.data?.processing_count) && (
              <span className="help-text">{pending.data?.processing_count} 项整理中</span>
            )}
            {pending.data && <span className="pending-count">{pending.data.items.length} 项</span>}
          </div>
        </div>
        {pending.isPending ? (
          <p className="muted-text" role="status">
            正在读取…
          </p>
        ) : pending.isError ? (
          <Feedback error={pending.error} />
        ) : pending.data.items.length ? (
          <div className="capture-queue">
            {pending.data.items.map((item) => (
              <CaptureRow key={item.id} item={item} />
            ))}
          </div>
        ) : (
          <div className="pending-empty">暂无待审阅的收集记录。</div>
        )}
      </section>
      <LedgerPending />
    </section>
  );
}
