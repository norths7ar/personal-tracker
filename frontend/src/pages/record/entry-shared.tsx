import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const today = () => new Intl.DateTimeFormat("en-CA").format(new Date());

export const selectClass =
  "h-9 w-full rounded-md border border-neutral-300 bg-white px-3 text-sm outline-none focus:border-neutral-500 focus:ring-2 focus:ring-neutral-200";

export const textareaClass =
  "min-h-24 w-full rounded-md border border-neutral-300 p-3 text-sm outline-none focus:border-neutral-500 focus:ring-2 focus:ring-neutral-200";

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
    <label className={cn("block space-y-1.5 text-sm font-medium", className)}>
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Feedback({
  message,
  error,
}: {
  message?: string;
  error?: Error | null;
}) {
  return (
    <>
      {message && (
        <p
          role="status"
          className="mt-4 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
        >
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-4 text-sm text-red-600">
          {error.message}
        </p>
      )}
    </>
  );
}
