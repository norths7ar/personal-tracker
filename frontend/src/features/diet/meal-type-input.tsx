import { useQuery } from "@tanstack/react-query";
import { useId, type ComponentProps } from "react";
import { settingsApi } from "@/api/client";
import { Input } from "@/components/ui/input";

export function MealTypeInput(props: ComponentProps<typeof Input>) {
  const listId = useId();
  const options = useQuery({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
    select: (settings) => settings.records.meal_types,
  });
  return (
    <>
      <Input {...props} list={listId} />
      <datalist id={listId}>
        {options.data?.map((label) => (
          <option key={label} value={label} />
        ))}
      </datalist>
    </>
  );
}
