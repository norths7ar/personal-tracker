# Personal Tracker

一个自用的记账与饮食记录工具。把日常支出和吃了什么记在一起，方便录入，也方便回看。项目围绕自己的使用习惯持续调整，以桌面浏览器为主要使用界面。

## 功能

- **日常记录**：用自然语言录入收支和饮食，通过 LLM 提取结构化信息，也可以手动填写、编辑和批量整理。
- **账目管理**：记录收入、支出和关联退款，管理一次性付款计划、周期付款与预付摊销。
- **饮食记录**：保留原始描述，记录用餐时间、食物和主要食材，查看时间分布与食物频次。
- **统计分析**：按时间和分类查看收支，区分实际支付与按月摊销的成本，并提供月度预算参考。

付款计划与实际交易分开记录，确认付款后才计入账目；摊销只改变费用归属月份，不产生额外付款。关联退款抵扣原支出，不重复计作收入。饮食统计基于已有记录，不把缺失记录当作没有进食，也不推断营养摄入。

## 实现

前端使用 React、TypeScript 和 Vite，图表使用 ECharts；后端使用 FastAPI，数据存储在本机 SQLite 数据库中。前端 API 类型由后端 OpenAPI 定义生成。

应用在本地运行，不依赖云端数据库。自然语言解析会将输入内容发送给配置的 LLM 服务，因此并非完全离线。模型与分类配置位于 `config.yaml`，密钥通过 `.env` 配置，真实数据与密钥不纳入 Git。

## 本地运行

日常运行环境为 Windows，使用 PowerShell 7、uv 和 Node.js/npm。在项目根目录准备环境：

```powershell
uv sync
npm --prefix frontend ci
npm --prefix frontend run build
Copy-Item .env.example .env
```

在 `.env` 中填写 `LLM_API_KEY`，并按需调整 `config.yaml` 中的模型配置，然后启动：

```powershell
.\scripts\personal-tracker-service.ps1 start
```

浏览器访问 <http://127.0.0.1:18080>。服务脚本支持 `status`、`stop`、`restart`，以及通过 `install-autostart` 设置登录后自动启动。更新代码后重新同步依赖、构建前端并重启服务。

默认数据库为 `data/expenses.db`，可通过 `.env` 中的 `DATABASE_PATH` 修改。备份脚本 `scripts/backup-personal-tracker.ps1` 支持 `run` 手动备份和 `install-schedule` 定时备份；使用 SQLite 原生备份接口，默认保存至 `data/backup/rolling`，保留最近 30 份。恢复前先停止服务、另存当前数据库，再用备份替换配置的数据库文件。

## 开发

先停止后台服务，再在两个终端分别运行后端 `uv run uvicorn api.main:app --host 127.0.0.1 --port 18080 --reload` 和前端 `npm --prefix frontend run dev`。后端运行时，可用 `npm --prefix frontend run generate:api` 更新 API 类型。

Python 使用 Ruff 检查与格式化，前端使用 ESLint、Prettier 和 TypeScript。测试集中保护数据库写入的原子性、重复提交、退款约束、摊销关联与备份，可通过 `uv run python -m unittest discover -s tests -v` 运行。
