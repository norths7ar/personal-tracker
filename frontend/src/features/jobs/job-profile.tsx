import { Button, Flex, Text, TextArea } from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { jobsApi } from "@/api/jobs";
import { JobError, JobField } from "./job-fields";
import { formatJobTime, JOB_PROFILE_QUERY_KEY } from "./job-options";

type ProfileDraft = Partial<Parameters<typeof jobsApi.saveProfile>[0]>;

export function JobProfilePanel() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: JOB_PROFILE_QUERY_KEY, queryFn: jobsApi.profile });
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
      queryClient.setQueryData(JOB_PROFILE_QUERY_KEY, value);
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
    <section className="content-panel jobs-profile-panel" aria-labelledby="jobs-profile-title">
      <div className="jobs-section-head">
        <h2 className="section-title" id="jobs-profile-title">
          求职资料
        </h2>
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
            disabled={busy}
            onClick={() => input.current?.click()}
          >
            <Upload size={15} /> 导入 DOCX
          </Button>
          {draft.imported_filename ? (
            <Text size="2" color="gray">
              已读入 {draft.imported_filename}，保存后生效
            </Text>
          ) : profile?.imported_filename ? (
            <Text size="2" color="gray">
              {profile.imported_filename}
              {profile.imported_at && ` · ${formatJobTime(profile.imported_at)}`}
            </Text>
          ) : null}
        </Flex>
      </div>

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
          <JobError error={preview.error} />
          <fieldset disabled={busy} className="jobs-fields">
            <JobField label="简历正文">
              <TextArea
                rows={16}
                placeholder="可导入 .docx 自动提取，或直接粘贴修改简历全文"
                value={resume}
                onChange={(event) => {
                  const value = event.target.value;
                  setDraft((current) => ({ ...current, resume_text: value }));
                }}
              />
            </JobField>
            <JobField label="给 AI 的私密补充">
              <TextArea
                rows={8}
                placeholder="求职底线（城市、薪资、工作强度、排斥项）、简历未体现的技能或近期计划"
                value={notes}
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
            <Button type="submit" loading={save.isPending} disabled={!dirty || busy}>
              保存资料
            </Button>
          </Flex>
        </form>
      )}
    </section>
  );
}
