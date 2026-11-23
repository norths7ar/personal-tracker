import { Button, Callout, Flex, Text } from "@radix-ui/themes";
import { useState, type ReactNode } from "react";
import { ApiError } from "@/api/client";

export function Field({
  label,
  children,
  error,
  hint,
}: {
  label: string;
  children: ReactNode;
  error?: string;
  hint?: string;
}) {
  return (
    <label className="settings-field">
      <Text size="2" weight="medium">
        {label}
      </Text>
      {children}
      {hint && (
        <Text size="1" color="gray">
          {hint}
        </Text>
      )}
      {error && (
        <Text size="1" color="red" role="alert">
          {error}
        </Text>
      )}
    </label>
  );
}

export function SaveFooter({
  pending,
  dirty,
  error,
  saved,
  onReload,
}: {
  pending: boolean;
  dirty: boolean;
  error: Error | null;
  saved: boolean;
  onReload: () => Promise<void>;
}) {
  const [reloading, setReloading] = useState(false);
  const [reloadError, setReloadError] = useState("");
  const conflict = error instanceof ApiError && error.status === 409;
  return (
    <div className="settings-save">
      {error && (
        <Callout.Root color="red" role="alert">
          <Callout.Text>
            {conflict
              ? "设置已在其他位置更新，当前修改尚未保存。请重新载入本组设置后编辑。"
              : error.message}
          </Callout.Text>
        </Callout.Root>
      )}
      <Flex align="center" gap="3" wrap="wrap">
        <Button type="submit" loading={pending} disabled={!dirty || reloading}>
          保存设置
        </Button>
        {saved && !dirty && (
          <Text size="2" color="gray" role="status">
            已保存并生效
          </Text>
        )}
        {conflict && (
          <Button
            type="button"
            variant="soft"
            loading={reloading}
            onClick={async () => {
              setReloadError("");
              setReloading(true);
              try {
                await onReload();
              } catch (reason) {
                setReloadError(reason instanceof Error ? reason.message : "重新载入失败");
              } finally {
                setReloading(false);
              }
            }}
          >
            放弃本组修改并重新载入
          </Button>
        )}
      </Flex>
      {reloadError && (
        <Text size="2" color="red" role="alert">
          {reloadError}
        </Text>
      )}
    </div>
  );
}
