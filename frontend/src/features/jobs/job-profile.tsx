import { Button, Flex, Text, TextArea } from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { jobsApi } from "@/api/jobs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { JobError, JobField } from "./job-fields";
import { formatJobTime } from "./job-options";

const profileKey = ["jobs", "profile"];
type ProfileDraft = Partial<Parameters<typeof jobsApi.saveProfile>[0]>;

export function JobProfileDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: profileKey, queryFn: jobsApi.profile, enabled: open });
  const [draft, setDraft] = useState<ProfileDraft>({});
  const input = useRef<HTMLInputElement>(null);
  const profile = query.data;
  const resume = draft.resume_text ?? profile?.resume_text ?? "";
  const notes = draft.supplemental_notes ?? profile?.supplemental_notes ?? "";
  const dirty =
    draft.imported_filename !== undefined ||
    resume !== profile?.resume_text ||
    notes !== profile?.supplemental_notes;
  const save = useMutation({
    mutationFn: jobsApi.saveProfile,
    onSuccess: (value) => {
      queryClient.setQueryData(profileKey, value);
      setDraft({});
      void queryClient.invalidateQueries({ queryKey: ["jobs", "detail"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs", "list"] });
    },
  });
  const preview = useMutation({
    mutationFn: jobsApi.previewDocx,
    onSuccess: (value) => {
      setDraft((current) => ({
        ...current,
        resume_text: value.resume_text,
        imported_filename: value.source_filename,
      }));
      save.reset();
    },
  });
  const busy = save.isPending || preview.isPending;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !busy) onClose();
      }}
    >
      <DialogContent layout="center" className="jobs-dialog">
        <DialogHeader>
          <DialogTitle>求职资料</DialogTitle>
          <DialogDescription>用于匹配分析和继续追问，不会自动发送给招聘方。</DialogDescription>
        </DialogHeader>
        {query.isPending && (
          <p className="loading-message" role="status">
            正在读取求职资料…
          </p>
        )}
        {query.isError && (
          <Flex align="center" gap="2" wrap="wrap">
            <JobError error={query.error} />
            <Button type="button" size="1" variant="soft" onClick={() => void query.refetch()}>
              重试
            </Button>
          </Flex>
        )}
        {profile && (
          <form
            className="jobs-fields"
            onSubmit={(event) => {
              event.preventDefault();
              if (!busy && dirty) {
                save.mutate({
                  resume_text: resume,
                  supplemental_notes: notes,
                  imported_filename: draft.imported_filename,
                });
              }
            }}
          >
            <fieldset disabled={busy} className="jobs-fields">
              <Flex gap="2" align="center" wrap="wrap">
                <input
                  type="file"
                  accept=".docx"
                  ref={input}
                  hidden
                  onChange={(event) => {
                    const file = event.currentTarget.files?.[0];
                    event.currentTarget.value = "";
                    if (file) preview.mutate(file);
                  }}
                />
                <Button
                  type="button"
                  variant="soft"
                  loading={preview.isPending}
                  onClick={() => input.current?.click()}
                >
                  <Upload size={15} /> 导入 DOCX
                </Button>
                {draft.imported_filename ? (
                  <Text size="2" color="gray">
                    已读入 {draft.imported_filename}，保存后生效
                  </Text>
                ) : profile.imported_filename ? (
                  <Text size="2" color="gray">
                    {profile.imported_filename}
                    {profile.imported_at && ` · ${formatJobTime(profile.imported_at)} 导入`}
                  </Text>
                ) : null}
              </Flex>
              <JobError error={preview.error} />
              <JobField label="简历正文">
                <TextArea
                  rows={12}
                  value={resume}
                  onChange={(event) => {
                    const value = event.target.value;
                    setDraft((current) => ({ ...current, resume_text: value }));
                  }}
                />
              </JobField>
              <JobField label="给 AI 的私密补充">
                <TextArea
                  rows={5}
                  value={notes}
                  placeholder="例如岗位偏好、实情或不适合写进简历的背景"
                  onChange={(event) => {
                    const value = event.target.value;
                    setDraft((current) => ({ ...current, supplemental_notes: value }));
                  }}
                />
              </JobField>
            </fieldset>
            <JobError error={save.error} />
            <Flex align="center" gap="2" wrap="wrap" justify="end">
              {save.isSuccess && !dirty && (
                <Text role="status" size="2" color="gray">
                  已保存
                </Text>
              )}
              <Button type="button" variant="soft" onClick={onClose} disabled={busy}>
                关闭
              </Button>
              <Button type="submit" loading={save.isPending} disabled={!dirty || busy}>
                保存资料
              </Button>
            </Flex>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
