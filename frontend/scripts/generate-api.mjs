import { spawnSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString, COMMENT_HEADER } from "openapi-typescript";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const root = resolve(frontend, "..");
const stamp = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" })
  .format(new Date())
  .replaceAll("-", "");
const scratch = resolve(root, ".tmp");
await mkdir(scratch, { recursive: true });
const exported = spawnSync(
  "uv",
  ["run", "--no-sync", "--project", root, "python", resolve(root, "scripts/export_openapi.py")],
  {
    cwd: root,
    encoding: "utf8",
    maxBuffer: 10 * 1024 * 1024,
  },
);
if (exported.error || exported.status !== 0) {
  throw new Error(exported.error?.message ?? exported.stderr ?? "OpenAPI 导出失败");
}
const schema = JSON.parse(exported.stdout);
await writeFile(resolve(scratch, `${stamp}-openapi.json`), JSON.stringify(schema, null, 2) + "\n");
const output = COMMENT_HEADER + astToString(await openapiTS(schema));
await writeFile(resolve(frontend, "src/api/schema.d.ts"), output);
console.log("API 类型已从后端 OpenAPI 生成，未启动服务。");
