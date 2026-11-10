# Personal Tracker

一个自用的记账、饮食记录与待办工具。记录日常支出和吃了什么，也留住想推进的事情。项目围绕自己的使用习惯持续调整，以桌面浏览器为主要使用界面。

## 功能

- **待办事项**：记下想做的事，调整顺序，选一件开始；支持完成、恢复和编辑，不要求分类或设定期限。
- **日常记录**：用自然语言录入收支和饮食，通过 LLM 提取结构化信息，也可以手动填写、编辑和批量整理。
- **账目管理**：记录收入、支出和关联退款，管理一次性付款计划、周期付款与预付摊销。
- **饮食记录**：保留原始描述，记录用餐时间、食物和主要食材，查看时间分布与食物频次。
- **统计分析**：按时间和分类查看收支，区分实际支付与按月摊销的成本，并提供月度预算参考。
- **设置**：在页面管理模型服务、密钥、分类、餐顿标签与访问密码；分类修改仅影响今后的选项，不修改历史记录。

付款计划与实际交易分开记录，确认付款后才计入账目；摊销只改变费用归属月份，不产生额外付款。关联退款抵扣原支出，不重复计作收入。饮食统计基于已有记录，不把缺失记录当作没有进食，也不推断营养摄入。

## 实现

前端使用 React、TypeScript、Radix Themes 和 Vite，图表使用 ECharts；后端使用 FastAPI，数据存储在本机 SQLite 数据库中。前端 API 类型由后端 OpenAPI 定义生成。

应用在本地运行，不依赖云端数据库。自然语言解析会将输入内容发送给配置的 LLM 服务，因此并非完全离线。配置保存在独立的 `data/settings.db`，API Key 加密保存，主密钥为 `data/.key`，登录密码保存校验摘要。真实数据与凭据不纳入 Git，不再读取 `.env` 或 `config.yaml`。

## 本地运行

日常运行环境为 Windows，使用 Python 3.14、uv、Node.js 24+ 和 pnpm。在项目根目录准备环境：

```powershell
uv sync
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
uv run python -m service start
```

浏览器访问 <http://127.0.0.1:18080>，在「设置」填写模型服务与 API Key。新实例默认不启用访问密码；启用后可修改密码或使其他登录失效。模型、分类与访问设置保存后生效，不中断已经发出的模型请求。

服务管理程序支持 `start`、`stop`、`restart`、`status`。生命周期由本项目管理，外部管理软件只调用[服务接口](docs/service-management.md)，不直接控制进程或内部运行文件。没有登录自启或定时备份任务。更新依赖后同步环境，前端更新后重新构建，再按需重启。

业务数据库固定为 `data/expenses.db`，设置页只读显示位置。备份时停止服务并保存整个 `data` 目录，尤其应配套保留 `settings.db` 与 `.key`；密钥丢失不能解密已有凭据。恢复前另存当前数据，使用配套备份恢复，不用新密钥覆盖旧密钥。若只需账目快照，可运行 `uv run python -m scripts.backup_sqlite`，默认保存到 `data/backups/rolling`；需要长期保留的历史备份放在 `data/backups/archive`，不参与滚动清理。

## 开发

开发时先停止占用端口的后台实例，再分别运行 `uv run uvicorn api.main:app --host 127.0.0.1 --port 18080 --reload` 和 `pnpm --dir frontend dev`。隔离验证可用服务管理程序的 `--data-path` 和 `--port` 指定独立实例；直接运行后端时使用 `TRACKER_DATA_DIR`，前端开发代理可通过 `VITE_API_PROXY` 指向隔离端口。这些是实例启动参数，不是页面中的数据位置设置。

`pnpm --dir frontend generate:api` 离线生成 API 类型，不启动服务或初始化数据。Python 使用 Ruff（行宽 100），执行 `uv run ruff check .` 和 `uv run ruff format --check .`；前端使用 ESLint、Prettier 和 tsc，分别提供 `lint`、`format:check`、`type-check` 命令。`uv run python -m unittest discover -s tests -v` 检查数据库写入、关联一致性、备份与开销统计；`pnpm --dir frontend test` 检查净支出及累计走势计算。

VS Code 直接打开仓库根目录，项目设置使用 `.venv` 解释器及仓库导入路径；保存行为、默认格式化器和 Pylance 诊断级别沿用用户配置。前端项目规则与工具版本由仓库配置及锁文件确定。
