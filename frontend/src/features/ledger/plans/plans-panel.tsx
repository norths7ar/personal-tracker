import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Feedback } from "@/features/record/entry-shared";
import { ExpectedForm } from "./expected-form";
import { ExpectedTable } from "./expected-table";
import type { ExpectedAction } from "./utils";
import "./plans-panel.css";

export function PlansPanel() {
  const [action, setAction] = useState<ExpectedAction | null>(null);
  const plans = useQuery({ queryKey: ["ledger", "plans"], queryFn: api.plans });
  return (
    <div className="page-stack">
      <div className="plans-toolbar">
        <p className="muted-text">一次性计划和周期付款都在这里管理，确认后才记入流水。</p>
        <Button onClick={() => setAction({ mode: "create" })}>
          <Plus size={16} />
          新增付款计划
        </Button>
      </div>
      {plans.isPending ? (
        <p className="muted-text">正在读取…</p>
      ) : plans.isError ? (
        <Feedback error={plans.error} />
      ) : (
        <ExpectedTable records={plans.data.expected} onAction={setAction} />
      )}
      <Dialog open={action !== null} onOpenChange={(open) => !open && setAction(null)}>
        <DialogContent>
          {action && <ExpectedForm action={action} onDone={() => setAction(null)} />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
