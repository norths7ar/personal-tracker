import type { ComponentPropsWithRef } from "react";

import { cn } from "@/lib/utils";
import { DateInput } from "./date-input";

export function Input({
  className,
  resetKey,
  ...props
}: ComponentPropsWithRef<"input"> & { resetKey?: string | number }) {
  if (props.type === "date")
    return <DateInput className={className} resetKey={resetKey} {...props} />;
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md border border-neutral-300 bg-white px-3 text-sm outline-none placeholder:text-neutral-400 focus:border-neutral-500 focus:ring-2 focus:ring-neutral-200",
        className,
      )}
      {...props}
    />
  );
}
