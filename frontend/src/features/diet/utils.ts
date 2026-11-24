import { type Meal } from "@/api/client";

export function foodLabel(food: Meal["foods"][number]): string {
  return `${food.food_name}${food.quantity ? `×${food.quantity}` : ""}`;
}

export function exportMeals(meals: Meal[]) {
  const rows = [
    ["ID", "日期", "时间", "餐顿", "描述", "食物", "备注"],
    ...meals.map((meal) => [
      meal.id,
      meal.date,
      meal.time ?? "",
      meal.meal_type ?? "",
      meal.description,
      meal.foods
        .map(
          (food) =>
            `${foodLabel(food)}${food.ingredients?.length ? `（${food.ingredients.join("、")}）` : ""}`,
        )
        .join("、"),
      meal.notes ?? "",
    ]),
  ];
  const csv = rows
    .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))
    .join("\r\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
  link.download = "diet.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}
