import { TextField } from "@radix-ui/themes";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

import { DateInput } from "./date-input";

export function Input({
  className,
  resetKey,
  ...props
}: ComponentProps<typeof TextField.Root> & { resetKey?: string | number }) {
  if (props.type === "date")
    return <DateInput className={className} resetKey={resetKey} {...props} />;
  return <TextField.Root className={cn("form-input", className)} {...props} />;
}
