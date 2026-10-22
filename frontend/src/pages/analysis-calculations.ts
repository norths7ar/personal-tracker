export function netExpense(row: { expense: number; income: number }) {
  return (Math.round(row.expense * 100) - Math.round(row.income * 100)) / 100;
}

export function cumulativeNetExpense(
  rows: { date: string; expense: number; income: number }[],
) {
  let total = 0;
  return rows.map((row) => {
    total += Math.round(netExpense(row) * 100);
    return { ...row, expense: total / 100 };
  });
}
