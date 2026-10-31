import "@/styles/entry-shared.css";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const today = () => new Intl.DateTimeFormat("en-CA").format(new Date());

export const selectClass = "form-select";

export const textareaClass = "form-textarea";

export function Field({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={cn("form-field", className)}>
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Feedback({ message, error }: { message?: string; error?: Error | null }) {
  return (
    <>
      {message && (
        <p role="status" className="feedback-success">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="feedback-error">
          {error.message}
        </p>
      )}
    </>
  );
}
