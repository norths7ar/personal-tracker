import type { Transaction } from "@/api/client";
import { cn } from "@/lib/utils";
import { Checkbox } from "@radix-ui/themes";
import { createColumnHelper } from "@tanstack/react-table";
import { formatMoney } from "./utils";
const columnHelper = createColumnHelper<Transaction>();
export const transactionColumns = [
  columnHelper.display({
    id: "select",
    header: ({ table }) => (
      <Checkbox
        aria-label="选择当前页"
        checked={
          table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() && "indeterminate")
        }
        onCheckedChange={(checked) => table.toggleAllPageRowsSelected(Boolean(checked))}
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        aria-label={`选择记录 ${row.original.id}`}
        checked={row.getIsSelected()}
        onCheckedChange={(checked) => row.toggleSelected(Boolean(checked))}
      />
    ),
    size: 40,
  }),
  columnHelper.accessor("date", { header: "日期", size: 110 }),
  columnHelper.accessor("type", {
    header: "类型",
    size: 85,
    cell: ({ getValue }) => (
      <span
        className={cn(
          "ledger-type",
          getValue() === "收入" && "ledger-type-income",
          getValue() === "迁移" && "ledger-type-transfer",
        )}
      >
        {getValue()}
      </span>
    ),
  }),
  columnHelper.accessor("description", { header: "描述", size: 360 }),
  columnHelper.accessor("amount", {
    header: "金额",
    cell: ({ getValue }) => formatMoney(getValue()),
    size: 110,
  }),
  columnHelper.accessor("category", { header: "主类别", size: 110 }),
  columnHelper.accessor("subcategory", { header: "子类别", size: 120 }),
  columnHelper.accessor("notes", { header: "备注", size: 220 }),
];
