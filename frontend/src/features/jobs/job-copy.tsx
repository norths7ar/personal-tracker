import { Button, Flex, TextArea } from "@radix-ui/themes";
import { Copy } from "lucide-react";
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { JobError } from "./job-fields";

export function JobCopyButton({
  label,
  load,
}: {
  label: string;
  load: () => string | Promise<string>;
}) {
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [fallback, setFallback] = useState<string | null>(null);
  const [error, setError] = useState<Error | string | null>(null);

  async function copy() {
    setBusy(true);
    setCopied(false);
    setError(null);
    try {
      const text = await load();
      try {
        await navigator.clipboard.writeText(text);
        setCopied(true);
      } catch {
        setFallback(text);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason : "读取内容失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Button size="2" variant="soft" type="button" loading={busy} onClick={() => void copy()}>
        <Copy size={14} /> {label}
        {copied && " · 已复制"}
      </Button>
      <JobError error={error} />
      <Dialog
        open={fallback !== null}
        onOpenChange={(open) => {
          if (!open) setFallback(null);
        }}
      >
        <DialogContent layout="center" className="jobs-dialog">
          <DialogHeader>
            <DialogTitle>{label}</DialogTitle>
            <DialogDescription>浏览器未允许访问剪贴板，请选择文本后手动复制。</DialogDescription>
          </DialogHeader>
          <TextArea
            aria-label="待复制的文本"
            readOnly
            rows={12}
            value={fallback ?? ""}
            onFocus={(event) => event.currentTarget.select()}
          />
          <Flex justify="end" mt="3">
            <Button variant="soft" onClick={() => setFallback(null)}>
              关闭
            </Button>
          </Flex>
        </DialogContent>
      </Dialog>
    </div>
  );
}
