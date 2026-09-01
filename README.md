# Personal Tracker

本地运行的个人记账与饮食记录工具。前端是 React，后端是 FastAPI，数据只保存在本机的 SQLite 文件中。

## 日常使用

首次准备环境：

```powershell
uv sync
Set-Location frontend
npm ci
npm run build
Set-Location ..
Copy-Item .env.example .env
```

在 `.env` 填入 `LLM_API_KEY`。默认数据文件是 `data/expenses.db`；它不纳入 Git。

安装一次登录后自动启动的本地服务：

```powershell
.\scripts\personal-tracker-service.ps1 install-autostart
```

服务只监听 `127.0.0.1:18080`，浏览器访问 <http://127.0.0.1:18080>。日常管理命令：

```powershell
.\scripts\personal-tracker-service.ps1 status
.\scripts\personal-tracker-service.ps1 restart
.\scripts\personal-tracker-service.ps1 stop
```

## 开发与更新

开发后端并使用 Vite 热更新时，分别运行：

```powershell
uv run uvicorn api.main:app --host 127.0.0.1 --port 18080 --reload
Set-Location frontend
npm run dev
```

Vite 会将 `/api` 代理到本地的 `18080` 端口。更新代码后：

```powershell
git pull
uv sync
Set-Location frontend
npm ci
npm run build
Set-Location ..
.\scripts\personal-tracker-service.ps1 restart
```

如需根据运行中的 API 更新前端类型定义：

```powershell
Set-Location frontend
npm run generate:api
```

## 数据备份

SQLite 备份使用数据库原生 backup API，不复制正在写入的数据库文件。安装每天 03:30 执行的滚动备份任务（保留最近 30 份）：

```powershell
.\scripts\backup-personal-tracker.ps1 install-schedule
```

备份文件位于 `data/backup/rolling`。可随时手动运行或查看任务：

```powershell
.\scripts\backup-personal-tracker.ps1 run
.\scripts\backup-personal-tracker.ps1 status
```

## 验证

```powershell
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
Set-Location frontend
npm run lint
npm run build
```

## 结构

- `api/`：FastAPI 路由与静态前端托管。
- `core/`：SQLite 数据访问、业务规则、LLM 提取和配置。
- `services/`：API 组合的业务服务。
- `frontend/`：React 用户界面。
- `scripts/`：本地服务与 SQLite 备份管理脚本。
- `data/`：本机 SQLite 数据及滚动备份，均被 Git 忽略。
