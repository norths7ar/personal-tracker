import { Badge, Button, Flex, Heading, Text, TextArea } from "@radix-ui/themes";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { settingsApi, type Settings } from "@/api/client";
import { SaveFooter } from "./fields";
import { validatePrompt } from "./prompt-template";
import { settingsQueryKey, useSectionRevision } from "./use-section-revision";

const labels = {
  expense_classifier: "消费分类",
  diet_extractor: "饮食提取",
  batch_blocks: "批量分块",
  batch_finance_events: "批量财务事件",
} as const;
type PromptName = keyof typeof labels;

export function PromptsSection({ settings }: { settings: Settings }) {
  return (
    <section className="settings-section" aria-labelledby="settings-prompts-title">
      <Heading as="h2" id="settings-prompts-title" size="4">
        提示词
      </Heading>
      {(Object.keys(labels) as PromptName[]).map((name) => (
        <PromptEditor key={name} name={name} settings={settings} />
      ))}
    </section>
  );
}

function PromptEditor({ name, settings }: { name: PromptName; settings: Settings }) {
  const queryClient = useQueryClient();
  const prompt = settings.prompts[name];
  const [draft, setDraft] = useState(prompt.text);
  const [savedText, setSavedText] = useState(prompt.text);
  const [validationError, setValidationError] = useState<string | null>(null);
  const dirty = draft !== savedText;
  const baseline = useSectionRevision(JSON.stringify(prompt), settings.revision, dirty, () => {
    setDraft(prompt.text);
    setSavedText(prompt.text);
    setValidationError(null);
  });
  const mutation = useMutation({
    mutationFn: (text: string | null) =>
      settingsApi.prompts({
        revision: baseline.revision(),
        prompts: { [name]: text },
      }),
    onSuccess: (next) => {
      baseline.accept(JSON.stringify(next.prompts[name]), next.revision);
      setDraft(next.prompts[name].text);
      setSavedText(next.prompts[name].text);
      setValidationError(null);
      queryClient.setQueryData(settingsQueryKey, next);
    },
  });
  return (
    <form
      className="settings-prompt"
      onSubmit={(event) => {
        event.preventDefault();
        const error = validatePrompt(draft, prompt.required_placeholders);
        setValidationError(error);
        if (!error) mutation.mutate(draft);
      }}
    >
      <Flex justify="between" align="center" gap="3" wrap="wrap">
        <Heading as="h3" size="3">
          {labels[name]}
        </Heading>
        <Badge color={prompt.customized ? "blue" : "gray"}>
          {prompt.customized ? "已自定义" : "内置默认"}
        </Badge>
      </Flex>
      <Text as="p" size="1" color="gray" id={`prompt-hint-${name}`}>
        占位符：{prompt.required_placeholders.map((item) => `\${${item}}`).join("、") || "无"}
      </Text>
      <TextArea
        aria-label={`${labels[name]}提示词`}
        aria-describedby={`prompt-hint-${name}`}
        value={draft}
        onChange={(event) => {
          setDraft(event.target.value);
          setValidationError(null);
        }}
        rows={18}
        disabled={mutation.isPending}
        className="settings-prompt-text"
        spellCheck={false}
      />
      {validationError && (
        <Text color="red" size="2" role="alert">
          {validationError}
        </Text>
      )}
      <SaveFooter
        pending={mutation.isPending}
        dirty={dirty}
        error={mutation.error}
        saved={mutation.isSuccess}
        onReload={async () => {
          const next = await settingsApi.get();
          baseline.accept(JSON.stringify(next.prompts[name]), next.revision);
          setDraft(next.prompts[name].text);
          setSavedText(next.prompts[name].text);
          setValidationError(null);
          mutation.reset();
          queryClient.setQueryData(settingsQueryKey, next);
        }}
        extraActions={
          <Button
            type="button"
            variant="soft"
            disabled={mutation.isPending || (!prompt.customized && !dirty)}
            onClick={() => {
              if (dirty && !window.confirm("恢复默认会放弃此项未保存的修改，是否继续？")) return;
              mutation.mutate(null);
            }}
          >
            恢复默认
          </Button>
        }
      />
    </form>
  );
}
