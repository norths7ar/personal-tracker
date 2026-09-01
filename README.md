# personal-tracker

个人记录工具，基于 React SPA、FastAPI、SQLite/PostgreSQL 和 OpenAI-compatible LLM。当前包含两条主线：开销记录与饮食记录。React 页面由 FastAPI 同域提供；应用可以在本地直接运行，也可以通过 Docker 部署到 NAS 或服务器。

## 功能

- **记录**：统一入口，包含批量录入、单笔开销录入和单餐饮食录入
  - 首页提醒三天内到期的预计支出和周期付款，并显示待分类数量
  - 批量录入会先把自然语言拆成语义事件，再分别进入开销/饮食 pipeline
  - 支持确认、编辑、跳过候选记录后批量保存
- **待处理**：集中处理待分类、低置信度或未知分类的支出
- **账目**：查询、筛选、编辑、删除和导出交易流水
  - 支持记录关联退款
  - 支持为支出设置摊销月数和摊销开始月份
  - 支持把已有支出设为周期性付款的首次记录
- **开销分析**：按月 / 年查看收支、日均、与上期对比和分类明细
  - 支持现金流和摊销后两种统计口径
  - 明细支持一级/二级分类聚合切换
  - 月分析提供基于分类变化的规则化趋势说明
  - 月视图可设置摊销后成本上限和实际付款的现金流上限
  - 单独显示活跃周期性付款折算后的月固定支出
- **跨期费用**：分为预计支出和预付摊销两个 tab
  - 预计支出可以是一次性或周期性；确认后才创建真实流水
  - 一次性计划可不设日期，周期性付款支持同日续费和固定天数续费
  - 预付摊销创建即记账，并把同一笔付款分摊到指定月份
- **饮食**：查看、编辑、删除、导出饮食记录，并按月查看用餐时间、餐次数和高频食物

开销记录支持：

- 支出描述自动调用 LLM 分类；低置信度或未知类别时进入手动确认
- 收入和迁移从 `config.yaml` 选择分类
- 迁移记录保存到流水，但不参与收支结余计算

饮食记录支持：

- 新饮食记录必须填写大概用餐时间（`HH:MM`）
- 用自然语言记录一餐，LLM 提取菜品、主要食材和可选餐顿标签
- 原始描述、菜品和食材分别保存；菜品及食材均可人工修正
- 餐顿标签允许留空；未明确填写时仅在典型时段内保守推断早餐、午餐或晚餐
- 低置信度时可手动确认

## 项目结构

```text
personal-tracker/
├── api/                    # FastAPI 应用、认证和 HTTP 路由
├── services/               # 页面工作流与 core 之间的编排层
├── frontend/               # Vite + React + TypeScript SPA
├── app.py                  # 暂时保留的 Streamlit 旧入口
├── config.yaml             # 开销分类、饮食配置和公开 LLM 参数
├── .env.example            # 环境变量示例
├── pyproject.toml          # 项目元数据和直接依赖
├── uv.lock                 # 完整、可复现的依赖锁定
├── requirements.txt        # 由 uv 生成，供 Streamlit Cloud 部署
├── core/
│   ├── config.py           # 配置加载
│   ├── db.py               # SQLite/PostgreSQL 连接和表初始化
│   ├── llm.py              # OpenAI-compatible LLM 调用封装
│   ├── subscription/
│   │   └── db.py           # 跨期费用（订阅/预付摊销）查询与维护
│   ├── planned_expense/
│   │   └── db.py           # 预计支出及其确认记账流程
│   ├── batch/
│   │   └── extractor.py    # 批量自然语言记录解析
│   ├── expense/
│   │   ├── classifier.py   # 开销分类逻辑
│   │   └── db.py           # 开销记录查询与统计
│   └── diet/
│       ├── extractor.py    # 饮食结构化提取逻辑
│       └── db.py           # 饮食记录查询与统计
├── pages/                  # 暂时保留的 Streamlit 旧页面
│   ├── batch_entry.py
│   ├── expense_pending.py
│   ├── expense_ledger.py
│   ├── expense_analysis.py
│   ├── subscriptions.py
│   └── diet_ledger.py
├── tests/
│   └── test_db_workflows.py
└── data/
    └── expenses.db         # 本地 SQLite 数据库，不进版本控制
```

## 快速开始

### 本地 SQLite

```powershell
uv sync

Copy-Item .env.example .env
# 编辑 .env，填入 LLM_API_KEY
# DB_BACKEND 保持 sqlite

Set-Location frontend
npm ci
npm run build
Set-Location ..

uv run uvicorn api.main:app --reload
```

打开 `http://127.0.0.1:8000`。FastAPI 会同域提供 `/api/*` 和已构建的 React 页面，直接访问 `/ledger` 等客户端路由也会返回 SPA。

开发前端时可以分别启动两个进程：根目录运行 `uv run uvicorn api.main:app --reload`，`frontend/` 目录运行 `npm run dev`。Vite 会把 `/api` 代理到本地 FastAPI。

### Docker 部署准备

镜像采用多阶段构建：Node 阶段生成 React 静态文件，Python 阶段运行单个 FastAPI 进程。基础镜像同时支持 x86_64 和 ARM64，可用于普通云服务器和极空间 Z2Pro。

先复制并填写环境变量：

```powershell
Copy-Item .env.example .env
```

部署时至少应设置 `AUTH_ENABLED=true`、`APP_PASSWORD`、独立的 `APP_SESSION_SECRET` 和 `LLM_API_KEY`。`APP_DATA_DIR` 指向宿主机上的持久化目录；NAS 上应使用绝对路径。默认对外端口为 `8080`，可以通过 `APP_PORT` 修改。Compose 只将这些运行所需变量传入容器，`.env` 中遗留的 Supabase 连接信息不会进入 NAS 容器。

```powershell
docker compose up --build -d
```

Compose 固定使用 SQLite，并将数据库保存为容器内的 `/app/data/expenses.db`。该目录来自宿主机的 `APP_DATA_DIR`，因此重建容器不会删除数据。当前 Compose 只定义应用本身；接入 NAS 上已有的 Tailscale 容器，需要确认其网络模式后再配置。

### 从 Supabase PostgreSQL 一次性迁移到 SQLite

该迁移只在切换至 NAS 前执行一次；运行中的容器不会连接或同步 Supabase。先在 Supabase 控制台保留一份可回滚备份，再在本地 `.env` 配置现有 PostgreSQL 连接信息（`DATABASE_URL` 或 Supabase pooler 三项）。随后执行：

```powershell
uv run python scripts/migrate_postgres_to_sqlite.py --target data/expenses.db
```

工具以只读方式读取 PostgreSQL，创建新的 SQLite 文件，保留原有主键，并逐表回读校验数据；还会执行 SQLite 的完整性与外键检查。目标文件已存在时会拒绝覆盖；只有明确传入 `--replace`，且新的转换成功后才会替换旧文件。将生成的 `data/expenses.db` 放在 NAS 的 `APP_DATA_DIR` 后，再启动 Compose。

### Supabase PostgreSQL / 旧 Streamlit 数据源

当前仍保留 Streamlit 旧入口代码作为迁移期回退。Supabase PostgreSQL 暂时作为既有数据源；迁移至 NAS 或服务器上的 SQLite 需要单独执行一次数据复制和一致性校验。

需要继续连接 Supabase 时，可以使用 PostgreSQL pooler connection string：

```toml
AUTH_ENABLED = "true"
DB_BACKEND = "postgres"
DATABASE_URL = "postgresql://postgres.<project-ref>:<password>@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"
APP_PASSWORD = "your_app_password"
LLM_API_KEY = "your_llm_api_key"
```

本地 `.env` 也可以使用完整 `DATABASE_URL`，或者用 Supabase 变量拼接 pooler URL：

```dotenv
AUTH_ENABLED=true
DB_BACKEND=postgres
SUPABASE_PROJECT_REF=your_project_ref
SUPABASE_PROJECT_PASSWORD=your_supabase_database_password
SUPABASE_POOLER_HOST=aws-0-ap-northeast-1.pooler.supabase.com
APP_PASSWORD=your_app_password
LLM_API_KEY=your_llm_api_key
```

`AUTH_ENABLED=false` 时不启用登录保护，适合本地开发。云端部署应设置 `AUTH_ENABLED=true` 和 `APP_PASSWORD`。

## 配置

`config.yaml` 包含：

- `支出`：支出主类别和子类别，供 LLM 分类和手动确认使用
- `收入`：收入分类
- `迁移`：还款、投资、提现、充值等不参与收支结余的流水分类
- `llm`：公开的 LLM 参数，包括 `base_url`、`model`、`temperature`、`max_tokens`、`timeout` 和统一置信度阈值
- `diet`：餐顿类型

`.env` 包含：

- `LLM_API_KEY`：必填，不能提交到版本控制的密钥
- `AUTH_ENABLED`：是否启用单用户登录保护，默认 `false`
- `APP_PASSWORD`：`AUTH_ENABLED=true` 时必填
- `APP_SESSION_SECRET`：会话签名密钥，部署时应与登录密码分开设置
- `COOKIE_SECURE`：通过 HTTPS 访问时设为 `true`
- `DB_BACKEND`：`sqlite` 或 `postgres`，默认 `sqlite`
- `DATABASE_PATH`：SQLite 文件路径；相对路径从项目根目录解析
- `DATABASE_URL`：PostgreSQL 连接 URL；云端部署推荐使用 Supabase pooler URL
- `SUPABASE_PROJECT_REF` / `SUPABASE_PROJECT_PASSWORD` / `SUPABASE_POOLER_HOST`：未设置 `DATABASE_URL` 时用于拼接 Supabase pooler URL

模型名、服务地址和推理参数统一在 `config.yaml` 的 `llm` 段配置；`.env` 只保存密钥。
部分 reasoning 模型可能忽略 `temperature` / `top_p` 等采样参数；例如 `mimo-v2.5` 思考模式会使用模型侧推荐默认值，因此这类模型主要通过 `max_tokens` 预留足够的推理和 JSON 输出预算。

分类配置会按 `config.yaml` 修改时间刷新，通常不需要重启服务。

## 技术栈

- UI：Vite + React + TypeScript、TanStack Query/Table、Tailwind、Radix、ECharts
- API：FastAPI，OpenAPI 自动生成前端 TypeScript 类型
- LLM：LangChain + OpenAI-compatible API
- 数据库：SQLite（本地默认）/ PostgreSQL（云端部署）
- 旧版回退：Streamlit 页面和依赖暂时保留，待 React 本地试用通过后再删除

## 测试

当前测试使用标准库 `unittest`：

```powershell
uv run python -m unittest discover -s tests -v
```

测试覆盖重点：

- SQLite 初始化和兼容迁移
- 旧摊销交易自动迁移为预付跨期费用
- 删除预付跨期费用时同步清空关联交易的摊销字段
- 金额写入和更新时同步维护 `amount_cents`
- 月度预算的保存、替换及现金流/摊销后口径对比
- 用餐时间规范化、必填校验和保守餐顿标签推断

复杂的会计语义、续费规则和界面边界记录在 `DECISIONS.md`。
