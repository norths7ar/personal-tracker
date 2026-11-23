import { zodResolver } from "@hookform/resolvers/zod";
import { Callout, Checkbox, Heading, Switch, Text, TextField } from "@radix-ui/themes";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { settingsApi, type Settings } from "@/api/client";
import { settingsQueryKey, useSectionRevision } from "./use-section-revision";
import { Field, SaveFooter } from "./fields";

export function AccessSection({ settings }: { settings: Settings }) {
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
      void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
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
            <Callout.Root color="gray">
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

const accessSchema = z.object({
  enabled: z.boolean(),
  password: z.string(),
  clear_password: z.boolean(),
  cookie_secure: z.boolean(),
  session_seconds: z.number().int("请输入整数秒数").positive("有效期必须大于 0"),
  reset_sessions: z.boolean(),
});

type AccessFormValues = z.infer<typeof accessSchema>;

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
