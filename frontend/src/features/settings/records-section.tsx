import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Flex, Heading, IconButton, Text, TextField } from "@radix-ui/themes";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";
import { settingsApi, type Settings } from "@/api/client";
import { settingsQueryKey, useSectionRevision } from "./use-section-revision";
import { SaveFooter } from "./fields";

export function RecordsSection({ settings }: { settings: Settings }) {
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
    },
  });
  return (
    <section className="settings-section" aria-labelledby="settings-records-title">
      <Heading as="h2" id="settings-records-title" size="4">
        记录选项
      </Heading>
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

function EditableLabel({
  value,
  onChange,
  onDelete,
  label,
  error,
  category = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onDelete: () => void;
  label: string;
  error?: string;
  category?: boolean;
}) {
  const [editing, setEditing] = useState(!value);
  const [original, setOriginal] = useState(value);
  const [empty, setEmpty] = useState(false);
  const finish = () => {
    if (!value.trim()) {
      setEmpty(true);
      return;
    }
    onChange(value.trim());
    setEmpty(false);
    setEditing(false);
  };
  const cancel = () => {
    if (!original) {
      onDelete();
      return;
    }
    onChange(original);
    setEmpty(false);
    setEditing(false);
  };
  return (
    <div className={category ? "settings-name-editor" : "settings-chip-editor"}>
      {editing ? (
        <div className="settings-inline-edit">
          <TextField.Root
            autoFocus
            aria-label={label}
            value={value}
            onChange={(event) => {
              onChange(event.target.value);
              setEmpty(false);
            }}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing) return;
              if (event.key === "Enter") {
                event.preventDefault();
                event.stopPropagation();
                finish();
              }
              if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                cancel();
              }
            }}
          />
          <IconButton
            type="button"
            size="1"
            variant="soft"
            aria-label={`确认${label}`}
            onClick={finish}
          >
            <Check size={14} />
          </IconButton>
          <IconButton
            type="button"
            size="1"
            variant="ghost"
            aria-label={`取消编辑${label}`}
            onClick={cancel}
          >
            <X size={14} />
          </IconButton>
          <IconButton
            type="button"
            size="1"
            variant="ghost"
            color="red"
            aria-label={`删除${label}`}
            onClick={onDelete}
          >
            <Trash2 size={14} />
          </IconButton>
        </div>
      ) : (
        <button
          type="button"
          className={category ? "settings-category-name" : "settings-chip"}
          aria-label={`编辑${label}：${value}`}
          onClick={() => {
            setOriginal(value);
            setEditing(true);
          }}
        >
          {value}
        </button>
      )}
      {(error || empty) && (
        <Text size="1" color="red" role="alert">
          {empty ? "名称不能为空" : error}
        </Text>
      )}
    </div>
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
      {name === "meal_types" && (
        <Text size="2" weight="medium">
          {label}
        </Text>
      )}
      <div className="settings-label-list">
        {rows.fields.map((row, index) => {
          const fieldName = `${name}.${index}.value` as const;
          const error = form.getFieldState(fieldName, form.formState).error;
          return (
            <Controller
              key={row.id}
              control={form.control}
              name={fieldName}
              render={({ field }) => (
                <EditableLabel
                  value={field.value}
                  onChange={field.onChange}
                  onDelete={() => rows.remove(index)}
                  label={`${label} ${index + 1}`}
                  error={error?.message}
                />
              )}
            />
          );
        })}
        <button
          className="settings-add-label"
          type="button"
          aria-label={`添加${label}`}
          onClick={() => rows.append({ value: "" })}
        >
          <Plus size={14} />
          添加
        </button>
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
    <details
      className="settings-categories"
      open={type === "支出" || Boolean(form.formState.errors[type])}
    >
      <summary>
        {type}分类 <span>{rows.fields.length}</span>
      </summary>
      <Flex align="center" justify="end" gap="3">
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
          <Controller
            control={form.control}
            name={`${type}.${index}.name`}
            render={({ field, fieldState }) => (
              <EditableLabel
                category
                value={field.value}
                onChange={field.onChange}
                onDelete={() => rows.remove(index)}
                label={`${type}分类 ${index + 1}`}
                error={fieldState.error?.message}
              />
            )}
          />
          <LabelRows
            key={`${type}.${index}.children`}
            name={`${type}.${index}.children`}
            label="子分类"
            form={form}
          />
        </div>
      ))}
    </details>
  );
}

const categoryTypes = ["支出", "收入", "迁移"] as const;

type CategoryType = (typeof categoryTypes)[number];

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
