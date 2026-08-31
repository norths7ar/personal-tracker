import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check, Minus } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Checkbox({ className, ...props }: ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      className={cn(
        "grid size-4 shrink-0 place-content-center rounded border border-neutral-400 bg-white data-[state=checked]:border-neutral-900 data-[state=checked]:bg-neutral-900 data-[state=indeterminate]:border-neutral-900 data-[state=indeterminate]:bg-neutral-900",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="text-white">
        {props.checked === "indeterminate" ? <Minus size={12} /> : <Check size={12} />}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
