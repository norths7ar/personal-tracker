import assert from "node:assert/strict";
import test from "node:test";

import {
  cumulativeNetExpense,
  netExpense,
} from "../src/pages/analysis-calculations.ts";

test("月度开销扣除收入，与 8000 元预算比较；收入较多时保留负值", () => {
  // 支出已由后端扣除关联退款，前端只再减接口返回的收入。
  const month = { expense: 9000, income: 1500 };
  assert.equal(netExpense(month), 7500);
  assert.equal(8000 - netExpense(month), 500);
  assert.equal(netExpense({ expense: 800, income: 300 }), 500);
  assert.equal(netExpense({ expense: 800, income: 0 }), 800);
  assert.equal(netExpense({ expense: 800, income: 1000 }), -200);
});

test("月度曲线在收入到账时下降，最终金额与同月总额一致且不丢分", () => {
  const daily = [
    { date: "2025-09-01", expense: 3000, income: 0 },
    { date: "2025-09-02", expense: 6000.01, income: 0 },
    { date: "2025-09-03", expense: 0, income: 1500.02 },
    { date: "2025-09-04", expense: 0, income: 8000 },
  ];
  const curve = cumulativeNetExpense(daily);
  assert.deepEqual(
    curve.map((point) => point.expense),
    [3000, 9000.01, 7499.99, -500.01],
  );
  // 年度各月金额和页面总额使用同一个 netExpense 计算。
  assert.equal(
    curve.at(-1).expense,
    netExpense({ expense: 9000.01, income: 9500.02 }),
  );
});
