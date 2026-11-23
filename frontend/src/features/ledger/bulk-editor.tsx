import { TextArea } from "@radix-ui/themes";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Transaction } from "@/api/client";
import { BulkFieldToggle, EditorFooter } from "@/components/record-actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { commonValue, formatMoney, selectClass, unique } from "./utils";
import { LockedField } from "./transaction-editor";
import { FormField } from "./fields";

export function BulkTransactionEditor({
  transactions,
  categories,
  onClose,
  onSaved,
}: {
  transactions: Transaction[];
  categories: Record<string, Record<string, string[]>>;
  onClose: () => void;
  onSaved: (changes: Partial<Pick<Transaction, "category" | "subcategory" | "notes">>) => void;
}) {
  const ids = transactions.map((transaction) => transaction.id);
  const selectedTypes = unique(transactions.map((transaction) => transaction.type));
  const transactionType = selectedTypes.length === 1 ? selectedTypes[0] : null;
  const initialCategory =
    commonValue(transactions.map((transaction) => transaction.category)) ?? "";
  const initialSubcategory =
    commonValue(transactions.map((transaction) => transaction.subcategory)) ?? "";
  const initialNotes = commonValue(transactions.map((transaction) => transaction.notes)) ?? "";
  const [changeCategory, setChangeCategory] = useState(false);
  const [changeNotes, setChangeNotes] = useState(false);
  const [category, setCategory] = useState(initialCategory);
  const [subcategory, setSubcategory] = useState(initialSubcategory);
  const [notes, setNotes] = useState(initialNotes);
  const categoryOptions = Object.keys(categories[transactionType ?? ""] ?? {});
  const subcategoryOptions = categories[transactionType ?? ""]?.[category] ?? [];
  const changes: Partial<Pick<Transaction, "category" | "subcategory" | "notes">> = {};
  if (changeCategory) {
    changes.category = category || null;
    changes.subcategory = subcategory || null;
  }
  if (changeNotes) changes.notes = notes.trim() || null;
  const update = useMutation({
    mutationFn: () => api.updateTransactions(ids, changes),
    onSuccess: () => onSaved(changes),
  });
  const totalAmount = transactions.reduce((sum, transaction) => sum + transaction.amount, 0);
  const date = commonValue(transactions.map((transaction) => transaction.date));

  return (
    <Dialog open onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <DialogContent layout="center">
        <DialogHeader>
          <DialogTitle>编辑 {ids.length} 条账目</DialogTitle>
          <DialogDescription>
            不可安全批量修改的字段已锁定；只会保存你主动勾选的项目。
          </DialogDescription>
        </DialogHeader>
        <div className="form-stack">
          <div className="paired-fields">
            <LockedField label="类型" value={transactionType ?? "多种类型"} />
            <LockedField label="日期" value={date ?? "多个日期"} />
            <LockedField label="描述" value="多条记录，不可批量修改" />
            <LockedField label="金额" value={`合计 ${formatMoney(totalAmount)}`} />
          </div>

          <BulkFieldToggle
            label="修改分类"
            checked={changeCategory}
            disabled={!transactionType}
            onChange={setChangeCategory}
          />
          {!transactionType && (
            <p className="help-text">所选记录包含不同类型，无法共用同一套分类。</p>
          )}
          <div className="paired-fields">
            <FormField label="主类别">
              <select
                className={`${selectClass}`}
                value={category}
                disabled={!changeCategory}
                onChange={(event) => {
                  setCategory(event.target.value);
                  setSubcategory("");
                }}
              >
                <option value="">请选择</option>
                {categoryOptions.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </FormField>
            <FormField label="子类别">
              <select
                className={`${selectClass}`}
                value={subcategory}
                disabled={!changeCategory}
                onChange={(event) => setSubcategory(event.target.value)}
              >
                <option value="">无</option>
                {subcategoryOptions.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </FormField>
          </div>

          <BulkFieldToggle label="覆盖备注" checked={changeNotes} onChange={setChangeNotes} />
          <TextArea
            className="bulk-notes"
            value={notes}
            disabled={!changeNotes}
            placeholder="留空将清除所选记录的备注"
            onChange={(event) => setNotes(event.target.value)}
          />
          {update.isError && <p className="error-text">{update.error.message}</p>}
          <EditorFooter>
            <Button variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button
              onClick={() => update.mutate()}
              disabled={
                (!changeCategory && !changeNotes) ||
                (changeCategory && !category) ||
                update.isPending
              }
            >
              {update.isPending ? "保存中…" : `修改 ${ids.length} 条记录`}
            </Button>
          </EditorFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
