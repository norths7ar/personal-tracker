import { Dialog as ThemeDialog, IconButton } from "@radix-ui/themes";
import { X } from "lucide-react";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export const Dialog = ThemeDialog.Root;
export const DialogTrigger = ThemeDialog.Trigger;
export const DialogClose = ThemeDialog.Close;

export function DialogContent({
  className,
  children,
  layout = "side",
  ...props
}: ComponentProps<typeof ThemeDialog.Content> & { layout?: "side" | "center" }) {
  return (
    <ThemeDialog.Content
      className={cn(
        "editor-dialog",
        layout === "side" ? "editor-dialog-side" : "editor-dialog-center",
        className,
      )}
      {...props}
    >
      {children}
      <ThemeDialog.Close>
        <IconButton className="editor-dialog-close" variant="ghost" color="gray" aria-label="关闭">
          <X size={18} />
        </IconButton>
      </ThemeDialog.Close>
    </ThemeDialog.Content>
  );
}

export function DialogHeader({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("editor-dialog-header", className)} {...props} />;
}
export function DialogTitle(props: ComponentProps<typeof ThemeDialog.Title>) {
  return <ThemeDialog.Title size="5" {...props} />;
}
export function DialogDescription(props: ComponentProps<typeof ThemeDialog.Description>) {
  return <ThemeDialog.Description size="2" color="gray" {...props} />;
}
