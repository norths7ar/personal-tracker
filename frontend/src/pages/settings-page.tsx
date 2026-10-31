import { zodResolver } from "@hookform/resolvers/zod";
import {
  Badge,
  Button,
  Callout,
  Checkbox,
  Flex,
  Heading,
  IconButton,
  Switch,
  Text,
  TextArea,
  TextField,
} from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { settingsApi, type Settings } from "@/api/settings";

import "./settings-page.css";

const settingsQueryKey = ["settings"];
const categoryTypes = ["支出", "收入", "迁移"] as const;
type CategoryType = (typeof categoryTypes)[number];

const modelSchema = z.object({
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

const labelsSchema = z
  .array(z.object({ value: z.string().trim().min(1, "标签不能为空") }))
  .superRefine((labels, context) => {
    const seen = new Set<string>();
    labels.forEach(({ value }, index) => {
      if (seen.has(value)) {
        context.addIssue({ code: "custom", path: [index, "value"], message: "标签不能重复" });
      }
      seen.add(value);
    });
  });
const categoryRowSchema = z.object({
  name: z.string().trim().min(1, "分类名称不能为空"),
  children: labelsSchema,
});
const categoryListSchema = z.array(categoryRowSchema).superRefine((rows, context) => {
  const names = new Set<string>();
  rows.forEach((row, index) => {
    if (names.has(row.name)) {
      context.addIssue({ code: "custom", path: [index, "name"], message: "分类名称不能重复" });
    }
    names.add(row.name);
  });
});
const recordsSchema = z.object({
  支出: categoryListSchema,
  收入: categoryListSchema,
  迁移: categoryListSchema,
  meal_types: labelsSchema,
});
type RecordFormValues = z.infer<typeof recordsSchema>;

const accessSchema = z.object({
  enabled: z.boolean(),
  password: z.string(),
  clear_password: z.boolean(),
  cookie_secure: z.boolean(),
  session_seconds: z.number().int("请输入整数秒数").positive("有效期必须大于 0"),
  reset_sessions: z.boolean(),
});
type AccessFormValues = z.infer<typeof accessSchema>;

function modelValues(settings: Settings): ModelFormValues {
  return { ...settings.model, api_key: "", clear_key: false };
}

function recordValues(settings: Settings): RecordFormValues {
  const rows = (type: (typeof categoryTypes)[number]) =>
    Object.entries(settings.records.categories[type] ?? {}).map(([name, children]) => ({
      name,
      children: children.map((value) => ({ value })),
    }));
  return {
    支出: rows("支出"),
    收入: rows("收入"),
    迁移: rows("迁移"),
    meal_types: settings.records.meal_types.map((value) => ({ value })),
  };
}

function accessValues(settings: Settings): AccessFormValues {
  return {
    enabled: settings.access.enabled,
    cookie_secure: settings.access.cookie_secure,
    session_seconds: settings.access.session_seconds,
    password: "",
    clear_password: false,
    reset_sessions: false,
  };
}

// An update to another section can advance the revision without erasing this
// section's draft. A conflicting change to this section keeps its old revision.
function useSectionRevision(
  signature: string,
  revision: string,
  dirty: boolean,
  reset: () => void,
) {
  const baseline = useRef({ signature, revision });
  const resetRef = useRef(reset);
  useEffect(() => {
    resetRef.current = reset;
  }, [reset]);
  useEffect(() => {
    if (baseline.current.signature === signature) {
      baseline.current.revision = revision;
    } else if (!dirty) {
      baseline.current = { signature, revision };
      resetRef.current();
    }
  }, [signature, revision, dirty]);
  return {
    revision: () => baseline.current.revision,
    accept: (nextSignature: string, nextRevision: string) => {
      baseline.current = { signature: nextSignature, revision: nextRevision };
    },
  };
}

function Field({
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

function SaveFooter({
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
          <Text size="2" color="green" role="status">
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

export function SettingsPage() {
  const settings = useQuery({
    queryKey: settingsQueryKey,
    queryFn: settingsApi.get,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  return (
    <div className="settings-page">
      <header className="settings-heading">
        <Heading as="h1" size="7">
          设置
        </Heading>
        <Text size="2" color="gray">
          管理模型服务、记录选项和访问权限。
        </Text>
      </header>
      {settings.isPending && (
        <Text color="gray" role="status">
          正在载入设置…
        </Text>
      )}
      {settings.isError && (
        <Callout.Root color="red" role="alert">
          <Callout.Text>{settings.error.message}</Callout.Text>
          <Button variant="soft" onClick={() => void settings.refetch()}>
            重新载入
          </Button>
        </Callout.Root>
      )}
      {settings.data && (
        <>
          <nav className="settings-navigation" aria-label="设置分组">
            <a href="#settings-model-title">模型服务</a>
            <a href="#settings-records-title">记录选项</a>
            <a href="#settings-access-title">访问控制</a>
            <a href="#settings-data-title">本地数据</a>
          </nav>
          <ModelSection settings={settings.data} />
          <RecordsSection settings={settings.data} />
          <AccessSection settings={settings.data} />
          <section className="settings-section" aria-labelledby="settings-data-title">
            <Heading as="h2" id="settings-data-title" size="4">
              本地数据
            </Heading>
            <Text size="2" color="gray">
              数据位置固定，由本项目管理，不提供切换或搬迁入口。
            </Text>
            <dl className="settings-paths">
              <dt>数据目录</dt>
              <dd>{settings.data.data_directory}</dd>
              <dt>账目数据库</dt>
              <dd>{settings.data.database_path}</dd>
            </dl>
            <Text size="2" color="gray">
              完整恢复需要同时保留业务数据、设置文件和加密主密钥。请按项目说明备份整个数据目录。
            </Text>
          </section>
        </>
      )}
    </div>
  );
}

function ModelSection({ settings }: { settings: Settings }) {
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
        <Badge color={settings.api_key_configured ? "green" : "gray"}>
          {settings.api_key_configured ? "API Key 已配置" : "尚未配置 API Key"}
        </Badge>
      </Flex>
      <Text size="2" color="gray">
        自然语言解析使用此服务。保存后用于新的解析请求，不中断已经发出的请求。
      </Text>
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

function LabelRows({
  name,
  label,
  form,
}: {
  name: "meal_types" | `${CategoryType}.${number}.children`;
  label: string;
  form: ReturnType<typeof useForm<RecordFormValues>>;
}) {
  const rows = useFieldArray({ control: form.control, name });
  return (
    <div className="settings-labels">
      <Text size="2" weight="medium">
        {label}
      </Text>
      <div className="settings-label-list">
        {rows.fields.map((row, index) => {
          const fieldName = `${name}.${index}.value` as const;
          const error = form.getFieldState(fieldName, form.formState).error;
          return (
            <div className="settings-label-entry" key={row.id}>
              <div className="settings-label-input">
                <TextArea
                  {...form.register(fieldName)}
                  rows={1}
                  aria-label={`${label} ${index + 1}`}
                  placeholder={label}
                />
                {error && (
                  <Text size="1" color="red" role="alert">
                    {error.message}
                  </Text>
                )}
              </div>
              <IconButton
                type="button"
                variant="ghost"
                color="red"
                aria-label={`删除${label} ${index + 1}`}
                onClick={() => rows.remove(index)}
              >
                <Trash2 size={14} />
              </IconButton>
            </div>
          );
        })}
        <Button type="button" variant="soft" size="1" onClick={() => rows.append({ value: "" })}>
          <Plus size={14} />
          添加{label}
        </Button>
      </div>
    </div>
  );
}

function CategoryRows({
  type,
  form,
}: {
  type: CategoryType;
  form: ReturnType<typeof useForm<RecordFormValues>>;
}) {
  const rows = useFieldArray({ control: form.control, name: type });
  return (
    <div className="settings-categories">
      <Flex align="center" justify="between" gap="3">
        <Heading as="h3" size="3">
          {type}分类
        </Heading>
        <Button
          type="button"
          size="1"
          variant="soft"
          onClick={() => rows.append({ name: "", children: [] })}
        >
          <Plus size={14} />
          添加分类
        </Button>
      </Flex>
      {rows.fields.length === 0 && (
        <Text size="2" color="gray">
          暂无分类，可添加新的分类。
        </Text>
      )}
      {rows.fields.map((row, index) => (
        <div className="settings-category-row" key={row.id}>
          <Field label="分类名称" error={form.formState.errors[type]?.[index]?.name?.message}>
            <TextArea
              {...form.register(`${type}.${index}.name`)}
              rows={1}
              aria-label={`${type}分类 ${index + 1} 名称`}
            />
          </Field>
          <LabelRows
            key={`${type}.${index}.children`}
            name={`${type}.${index}.children`}
            label="子分类"
            form={form}
          />
          <IconButton
            type="button"
            variant="ghost"
            color="red"
            className="settings-remove-category"
            aria-label={`删除${type}分类 ${row.name || index + 1}`}
            onClick={() => rows.remove(index)}
          >
            <Trash2 size={16} />
          </IconButton>
        </div>
      ))}
    </div>
  );
}

function RecordsSection({ settings }: { settings: Settings }) {
  const queryClient = useQueryClient();
  const form = useForm<RecordFormValues>({
    resolver: zodResolver(recordsSchema),
    defaultValues: recordValues(settings),
  });
  const signature = JSON.stringify(settings.records);
  const baseline = useSectionRevision(signature, settings.revision, form.formState.isDirty, () =>
    form.reset(recordValues(settings)),
  );
  const mutation = useMutation({
    mutationFn: settingsApi.records,
    onSuccess: (next) => {
      baseline.accept(JSON.stringify(next.records), next.revision);
      form.reset(recordValues(next));
      queryClient.setQueryData(settingsQueryKey, next);
      void queryClient.invalidateQueries({ queryKey: ["categories"] });
      void queryClient.invalidateQueries({ queryKey: ["record-options"] });
    },
  });
  return (
    <section className="settings-section" aria-labelledby="settings-records-title">
      <Heading as="h2" id="settings-records-title" size="4">
        记录选项
      </Heading>
      <Text size="2" color="gray">
        分类修改只影响今后的可选项与解析，不修改历史账目。已使用的旧分类仍保留在原记录中。
      </Text>
      <form
        onSubmit={form.handleSubmit((values) =>
          mutation.mutate({
            revision: baseline.revision(),
            records: {
              categories: Object.fromEntries(
                categoryTypes.map((type) => [
                  type,
                  Object.fromEntries(
                    values[type].map((row) => [row.name, row.children.map(({ value }) => value)]),
                  ),
                ]),
              ),
              meal_types: values.meal_types.map(({ value }) => value),
            },
          }),
        )}
      >
        <fieldset disabled={mutation.isPending} className="settings-fields">
          {categoryTypes.map((type) => (
            <CategoryRows key={type} type={type} form={form} />
          ))}
          <LabelRows name="meal_types" label="餐顿标签" form={form} />
          <Text size="2" color="gray">
            每个输入框代表一个标签，标点保留在标签中。记录时仍可填写其他餐顿标签或留空。
          </Text>
        </fieldset>
        <SaveFooter
          pending={mutation.isPending}
          dirty={form.formState.isDirty}
          error={mutation.error}
          saved={mutation.isSuccess}
          onReload={async () => {
            const next = await settingsApi.get();
            baseline.accept(JSON.stringify(next.records), next.revision);
            form.reset(recordValues(next));
            mutation.reset();
            queryClient.setQueryData(settingsQueryKey, next);
          }}
        />
      </form>
    </section>
  );
}

function AccessSection({ settings }: { settings: Settings }) {
  const queryClient = useQueryClient();
  const form = useForm<AccessFormValues>({
    resolver: zodResolver(accessSchema),
    defaultValues: accessValues(settings),
  });
  const signature = JSON.stringify(settings.access);
  const baseline = useSectionRevision(signature, settings.revision, form.formState.isDirty, () =>
    form.reset(accessValues(settings)),
  );
  const mutation = useMutation({
    mutationFn: settingsApi.access,
    onSuccess: (next) => {
      baseline.accept(JSON.stringify(next.access), next.revision);
      form.reset(accessValues(next));
      queryClient.setQueryData(settingsQueryKey, next);
      void queryClient.invalidateQueries({ queryKey: ["current-user"] });
    },
  });
  const enabled = form.watch("enabled");
  const clearPassword = form.watch("clear_password");
  const secureCookie = form.watch("cookie_secure");
  return (
    <section className="settings-section" aria-labelledby="settings-access-title">
      <Heading as="h2" id="settings-access-title" size="4">
        访问控制
      </Heading>
      <Text size="2" color="gray">
        为应用设置访问密码。关闭密码保护不会删除记录或模型密钥。
      </Text>
      <form
        onSubmit={form.handleSubmit(({ password, clear_password, ...values }) => {
          if (
            values.enabled &&
            (clear_password || (!password && !settings.access.password_configured))
          ) {
            form.setError("password", { message: "启用密码保护前，请设置访问密码" });
            return;
          }
          if (values.enabled && values.cookie_secure && window.location.protocol !== "https:") {
            form.setError("cookie_secure", {
              message: "当前使用 HTTP，启用密码保护时请关闭仅 HTTPS Cookie",
            });
            return;
          }
          mutation.mutate({
            ...values,
            revision: baseline.revision(),
            password: clear_password ? "" : password || null,
          });
        })}
      >
        <fieldset disabled={mutation.isPending} className="settings-fields">
          <Controller
            control={form.control}
            name="enabled"
            render={({ field }) => (
              <Text as="label" size="2" className="settings-checkbox">
                <Switch
                  checked={field.value}
                  onCheckedChange={(value) => {
                    field.onChange(value);
                    if (value) form.setValue("clear_password", false, { shouldDirty: true });
                  }}
                />
                启用密码保护
              </Text>
            )}
          />
          <div className="settings-grid">
            <Field
              label="访问密码"
              hint={
                settings.access.password_configured
                  ? "已设置密码。留空保留，输入新密码则替换。"
                  : "尚未设置访问密码。"
              }
              error={form.formState.errors.password?.message}
            >
              <TextField.Root
                {...form.register("password")}
                type="password"
                autoComplete="new-password"
                disabled={clearPassword}
                placeholder="输入新的访问密码"
              />
            </Field>
            <Field
              label="登录有效期（秒）"
              hint="默认 2592000 秒，即 30 天。"
              error={form.formState.errors.session_seconds?.message}
            >
              <TextField.Root
                {...form.register("session_seconds", { valueAsNumber: true })}
                type="number"
                min="1"
                step="1"
              />
            </Field>
          </div>
          {settings.access.password_configured && !enabled && (
            <Controller
              control={form.control}
              name="clear_password"
              render={({ field }) => (
                <Text as="label" size="2" className="settings-checkbox">
                  <Checkbox
                    checked={field.value}
                    onCheckedChange={(value) => field.onChange(value === true)}
                  />
                  清除已保存的访问密码
                </Text>
              )}
            />
          )}
          <Controller
            control={form.control}
            name="cookie_secure"
            render={({ field }) => (
              <Text as="label" size="2" className="settings-checkbox">
                <Checkbox
                  checked={field.value}
                  onCheckedChange={(value) => field.onChange(value === true)}
                />
                登录 Cookie 仅通过 HTTPS 传输
              </Text>
            )}
          />
          <Text size="2" color="gray">
            本机 HTTP 访问应关闭此项；使用 HTTPS 入口时再启用。
          </Text>
          {form.formState.errors.cookie_secure && (
            <Text size="2" color="red" role="alert">
              {form.formState.errors.cookie_secure.message}
            </Text>
          )}
          {secureCookie && window.location.protocol !== "https:" && (
            <Callout.Root color="amber">
              <Callout.Text>
                当前页面使用 HTTP，不能同时启用密码保护和仅 HTTPS Cookie。需要此设置时，请从 HTTPS
                入口操作。
              </Callout.Text>
            </Callout.Root>
          )}
          <Controller
            control={form.control}
            name="reset_sessions"
            render={({ field }) => (
              <Text as="label" size="2" className="settings-checkbox">
                <Checkbox
                  checked={field.value}
                  onCheckedChange={(value) => field.onChange(value === true)}
                />
                保存时退出其他登录
              </Text>
            )}
          />
          <Text size="2" color="gray">
            保存访问配置后当前登录会更新；其他已失效的登录需要重新输入密码。会话签名密钥由应用管理。
          </Text>
        </fieldset>
        <SaveFooter
          pending={mutation.isPending}
          dirty={form.formState.isDirty}
          error={mutation.error}
          saved={mutation.isSuccess}
          onReload={async () => {
            const next = await settingsApi.get();
            baseline.accept(JSON.stringify(next.access), next.revision);
            form.reset(accessValues(next));
            mutation.reset();
            queryClient.setQueryData(settingsQueryKey, next);
          }}
        />
      </form>
    </section>
  );
}
