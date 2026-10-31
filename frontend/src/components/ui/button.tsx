import { Button as ThemeButton, IconButton } from "@radix-ui/themes";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

type ButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "color"> & {
  variant?: "default" | "outline" | "danger" | "ghost";
  size?: "default" | "sm" | "icon";
};

export function Button({
  variant = "default",
  size = "default",
  className,
  ...props
}: ButtonProps) {
  const visual = variant === "outline" ? "surface" : variant === "ghost" ? "ghost" : "solid";
  const color = variant === "danger" ? "red" : undefined;
  return size === "icon" ? (
    <IconButton
      type="submit"
      size="2"
      variant={visual}
      color={color}
      className={cn("app-button", className)}
      {...props}
    />
  ) : (
    <ThemeButton
      type="submit"
      size={size === "sm" ? "1" : "2"}
      variant={visual}
      color={color}
      className={cn("app-button", className)}
      {...props}
    />
  );
}
