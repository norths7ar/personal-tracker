import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { Feedback } from "@/features/record/entry-shared";
import { type ExpectedAction, type PrepaidAction } from "./utils";
import { ExpectedTable } from "./expected-table";
import { PrepaidTable } from "./prepaid-table";
import { ExpectedForm } from "./expected-form";
import { PrepaidForm } from "./prepaid-form";
import "./cross-period-page.css";

export function CrossPeriodPage() {
  const [tab, setTab] = useState<Tab>("expected");
  const [expectedAction, setExpectedAction] = useState<ExpectedAction | null>(null);
  const [prepaidAction, setPrepaidAction] = useState<PrepaidAction | null>(null);
  const data = useQuery({
    queryKey: ["ledger", "cross-period"],
    queryFn: api.crossPeriod,
  });

  return (
    <section className="page-stack cross-period-page">
      <header className="page-heading">
        <div>
          <h1 className="page-title">跨期费用</h1>
        </div>
        <Button
          onClick={() =>
            tab === "expected"
              ? setExpectedAction({ mode: "create" })
              : setPrepaidAction({ mode: "create" })
          }
        >
          <Plus size={16} />
          {tab === "expected" ? "新增预计支出" : "新增预付摊销"}
        </Button>
      </header>
      <div className="cross-period-toolbar">
        <div className="page-tabs">
          <TabButton active={tab === "expected"} onClick={() => setTab("expected")}>
            预计支出
          </TabButton>
          <TabButton active={tab === "prepaid"} onClick={() => setTab("prepaid")}>
            预付摊销
          </TabButton>
        </div>
        {data.data && (
          <span className="cross-period-count">
            {tab === "expected" ? data.data.expected.length : data.data.prepaid.length} 项
          </span>
        )}
      </div>
      {data.isPending ? (
        <p className="muted-text">正在读取…</p>
      ) : data.isError ? (
        <Feedback error={data.error} />
      ) : tab === "expected" ? (
        <ExpectedTable records={data.data.expected} onAction={setExpectedAction} />
      ) : (
        <PrepaidTable records={data.data.prepaid} onAction={setPrepaidAction} />
      )}

      <Dialog
        open={expectedAction !== null}
        onOpenChange={(open) => !open && setExpectedAction(null)}
      >
        <DialogContent>
          {expectedAction && (
            <ExpectedForm action={expectedAction} onDone={() => setExpectedAction(null)} />
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={prepaidAction !== null}
        onOpenChange={(open) => !open && setPrepaidAction(null)}
      >
        <DialogContent>
          {prepaidAction && (
            <PrepaidForm action={prepaidAction} onDone={() => setPrepaidAction(null)} />
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

type Tab = "expected" | "prepaid";

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button className={cn("page-tab", active && "page-tab-selected")} onClick={onClick}>
      {children}
    </button>
  );
}
