import { zodResolver } from "@hookform/resolvers/zod";
import { Badge, Checkbox, Flex, Heading, Switch, Text, TextField } from "@radix-ui/themes";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { settingsApi, type Settings } from "@/api/client";
import { settingsQueryKey, useSectionRevision } from "./use-section-revision";
import { Field, SaveFooter } from "./fields";

export function ModelSection({ settings }: { settings: Settings }) {
  const queryClient = useQueryClient();
  const form = useForm<ModelFormValues>({
    resolver: zodResolver(modelSchema),
    defaultValues: modelValues(settings),
  });
  const signature = JSON.stringify([settings.model, settings.api_key_configured]);
  const baseline = useSectionRevision(signature, settings.revision, form.formState.isDirty, () =>
    form.reset(modelValues(settings)),
  );
  const mutation = useMutation({
    mutationFn: settingsApi.model,
    onSuccess: (next) => {
      baseline.accept(JSON.stringify([next.model, next.api_key_configured]), next.revision);
      form.reset(modelValues(next));
      queryClient.setQueryData(settingsQueryKey, next);
    },
  });
  const errors = form.formState.errors;
  const clearKey = form.watch("clear_key");
  return (
    <section className="settings-section" aria-labelledby="settings-model-title">
      <Flex align="center" justify="between" gap="3" wrap="wrap">
        <Heading as="h2" id="settings-model-title" size="4">
          模型服务
        </Heading>
        <Badge color="gray">
          {settings.api_key_configured ? "API Key 已配置" : "尚未配置 API Key"}
        </Badge>
      </Flex>
      <form
        onSubmit={form.handleSubmit(({ api_key, clear_key, ...model }) =>
          mutation.mutate({
            revision: baseline.revision(),
            model,
            api_key: clear_key ? "" : api_key || null,
          }),
        )}
      >
        <fieldset disabled={mutation.isPending} className="settings-fields">
          <div className="settings-grid">
            <Field
              label="服务地址"
              error={errors.base_url?.message}
              hint="兼容 OpenAI API 的完整地址"
            >
              <TextField.Root
                {...form.register("base_url")}
                placeholder="https://api.example.com/v1"
              />
            </Field>
            <Field label="模型名称" error={errors.model?.message}>
              <TextField.Root {...form.register("model")} placeholder="填写服务商提供的模型名称" />
            </Field>
          </div>
          <Field label="API Key" hint="不会回显已保存的密钥。留空保留，输入新密钥则替换。">
            <TextField.Root
              {...form.register("api_key")}
              type="password"
              autoComplete="new-password"
              disabled={clearKey}
              placeholder={settings.api_key_configured ? "已配置，留空保留" : "输入 API Key"}
            />
          </Field>
          {settings.api_key_configured && (
            <Controller
              control={form.control}
              name="clear_key"
              render={({ field }) => (
                <Text as="label" size="2" className="settings-checkbox">
                  <Checkbox
                    checked={field.value}
                    onCheckedChange={(value) => field.onChange(value === true)}
                  />
                  清除已保存的 API Key
                </Text>
              )}
            />
          )}
          <details
            className="settings-advanced"
            open={Boolean(
              errors.temperature ||
              errors.max_tokens ||
              errors.timeout ||
              errors.confidence_threshold,
            )}
          >
            <summary>解析参数</summary>
            <Controller
              control={form.control}
              name="thinking"
              render={({ field }) => (
                <Text as="label" size="2" className="settings-checkbox">
                  <Switch
                    checked={field.value === "disabled"}
                    onCheckedChange={(checked) => field.onChange(checked ? "disabled" : "default")}
                  />
                  关闭模型思考
                </Text>
              )}
            />
            <Text as="p" size="1" color="gray">
              开启此项时明确关闭思考；关闭此项时遵循服务商默认行为，不代表强制开启思考。需服务商支持此参数。
            </Text>
            <div className="settings-grid settings-grid-four">
              <Field label="温度" error={errors.temperature?.message} hint="0–2，较低时输出更稳定">
                <TextField.Root
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  {...form.register("temperature", { valueAsNumber: true })}
                />
              </Field>
              <Field label="最大输出 Token" error={errors.max_tokens?.message}>
                <TextField.Root
                  type="number"
                  min="1"
                  step="1"
                  {...form.register("max_tokens", { valueAsNumber: true })}
                />
              </Field>
              <Field label="请求超时（秒）" error={errors.timeout?.message}>
                <TextField.Root
                  type="number"
                  min="0.01"
                  step="any"
                  {...form.register("timeout", { valueAsNumber: true })}
                />
              </Field>
              <Field
                label="识别置信度阈值"
                error={errors.confidence_threshold?.message}
                hint="0–1，低于阈值的结果需要确认"
              >
                <TextField.Root
                  type="number"
                  min="0"
                  max="1"
                  step="0.05"
                  {...form.register("confidence_threshold", { valueAsNumber: true })}
                />
              </Field>
            </div>
          </details>
        </fieldset>
        <SaveFooter
          pending={mutation.isPending}
          dirty={form.formState.isDirty}
          error={mutation.error}
          saved={mutation.isSuccess}
          onReload={async () => {
            const next = await settingsApi.get();
            baseline.accept(JSON.stringify([next.model, next.api_key_configured]), next.revision);
            form.reset(modelValues(next));
            mutation.reset();
            queryClient.setQueryData(settingsQueryKey, next);
          }}
        />
      </form>
    </section>
  );
}

const modelSchema = z.object({
  protocol: z.literal("openai_chat_completions"),
  thinking: z.enum(["default", "disabled"]),
  base_url: z
    .string()
    .trim()
    .url("请输入完整的服务地址")
    .refine((value) => {
      try {
        const url = new URL(value);
        return (
          ["http:", "https:"].includes(url.protocol) &&
          !url.username &&
          !url.password &&
          !url.search &&
          !url.hash
        );
      } catch {
        return false;
      }
    }, "请使用不含凭据、查询参数或片段的 HTTP 或 HTTPS 地址"),
  model: z.string().trim().min(1, "请输入模型名称"),
  temperature: z.number().min(0, "不能小于 0").max(2, "不能大于 2"),
  max_tokens: z.number().int("请输入整数").positive("请输入正数"),
  timeout: z.number().positive("请输入正数"),
  confidence_threshold: z.number().min(0, "不能小于 0").max(1, "不能大于 1"),
  api_key: z.string(),
  clear_key: z.boolean(),
});

type ModelFormValues = z.infer<typeof modelSchema>;

function modelValues(settings: Settings): ModelFormValues {
  return { ...settings.model, api_key: "", clear_key: false };
}
