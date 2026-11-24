import { Button, Callout, Heading, Text } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import { Database, Layers3, Settings2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { settingsApi } from "@/api/client";
import { settingsQueryKey } from "./use-section-revision";
import { ModelSection } from "./model-section";
import { RecordsSection } from "./records-section";
import { AccessSection } from "./access-section";
import { PromptsSection } from "./prompts-section";
import "./settings-page.css";

export function SettingsPage() {
  const [section, setSection] = useState("model");
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
        <Heading as="h1" className="page-title" size="7">
          设置
        </Heading>
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
        <div className="settings-workspace">
          <nav className="settings-navigation" aria-label="设置分组">
            {[
              { id: "model", label: "模型服务", icon: Settings2 },
              { id: "records", label: "记录选项", icon: Layers3 },
              { id: "prompts", label: "提示词", icon: Settings2 },
              { id: "access", label: "访问控制", icon: ShieldCheck },
              { id: "data", label: "本地数据", icon: Database },
            ].map(({ id, label, icon: Icon }) => (
              <button
                type="button"
                key={id}
                aria-pressed={section === id}
                aria-controls={`settings-panel-${id}`}
                onClick={() => setSection(id)}
              >
                <Icon size={18} />
                {label}
              </button>
            ))}
          </nav>
          <div className="settings-content">
            <div id="settings-panel-model" hidden={section !== "model"}>
              <ModelSection settings={settings.data} />
            </div>
            <div id="settings-panel-records" hidden={section !== "records"}>
              <RecordsSection settings={settings.data} />
            </div>
            <div id="settings-panel-access" hidden={section !== "access"}>
              <AccessSection settings={settings.data} />
            </div>
            <div id="settings-panel-prompts" hidden={section !== "prompts"}>
              <PromptsSection settings={settings.data} />
            </div>
            <div id="settings-panel-data" hidden={section !== "data"}>
              <section className="settings-section" aria-labelledby="settings-data-title">
                <Heading as="h2" id="settings-data-title" size="4">
                  本地数据
                </Heading>
                <dl className="settings-paths">
                  <dt>数据目录</dt>
                  <dd>{settings.data.data_directory}</dd>
                  <dt>账目数据库</dt>
                  <dd>{settings.data.database_path}</dd>
                </dl>
                <Text size="2" color="gray">
                  恢复备份时需同时保留业务库、设置库与加密主密钥（整个 data 目录）。
                </Text>
              </section>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
