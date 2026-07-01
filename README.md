# personal-tracker

本地运行的个人记录工具，基于 Streamlit、SQLite 和 OpenAI-compatible LLM。当前包含两条主线：开销记录与饮食记录。

## 功能

- **开销记录**：记录支出、收入、迁移三类账目
  - 支出描述自动调用 LLM 分类；低置信度或未知类别时进入手动确认
  - 收入和迁移从 `config.yaml` 选择分类
  - 迁移记录保存到流水，但不参与收支结余计算
- **开销流水**：支持按类型、主类别、子类别筛选，支持搜索描述、分类和备注，可导出 CSV、编辑和二次确认删除
- **开销分析**：按周 / 月 / 年查看收支、日均、与上期对比和分类明细；明细支持一级/二级分类聚合切换
- **饮食记录**：用自然语言记录一餐，LLM 提取餐顿类型和食物清单，低置信度时可手动确认
- **饮食查看与分析**：查看、编辑、删除、导出饮食记录，并按周/月查看覆盖率、餐顿分布和高频食物

## 项目结构

```text
personal-tracker/
├── app.py                  # Streamlit 入口和页面导航
├── config.yaml             # 开销分类、饮食配置和公开 LLM 参数
├── .env.example            # LLM 环境变量示例
├── requirements.txt        # Python 依赖
├── core/
│   ├── config.py           # 配置加载
│   ├── db.py               # SQLite 连接和表初始化
│   ├── llm.py              # OpenAI-compatible LLM 调用封装
│   ├── expense/
│   │   ├── classifier.py   # 开销分类逻辑
│   │   └── db.py           # 开销记录查询与统计
│   └── diet/
│       ├── extractor.py    # 饮食结构化提取逻辑
│       └── db.py           # 饮食记录查询与统计
├── pages/
│   ├── expense_entry.py
│   ├── expense_ledger.py
│   ├── expense_analysis.py
│   ├── diet_entry.py
│   ├── diet_ledger.py
│   └── diet_analysis.py
└── data/
    └── expenses.db         # 本地 SQLite 数据库，不进版本控制
```

## 快速开始

```powershell
conda create -n expense-tracker python=3.12
conda activate expense-tracker
pip install -r requirements.txt

Copy-Item .env.example .env
# 编辑 .env，填入 LLM_API_KEY

streamlit run app.py
```

如果 Python 不在 PATH 中，可以使用完整解释器路径启动：

```powershell
C:/Users/jnkyl/miniconda3/envs/expense-tracker/python.exe -m streamlit run app.py
```

## 配置

`config.yaml` 包含：

- `支出`：支出主类别和子类别，供 LLM 分类和手动确认使用
- `收入`：收入分类
- `迁移`：还款、投资、提现、充值等不参与收支结余的流水分类
- `llm`：公开的 LLM 参数，包括 `base_url`、`model`、`temperature`、`max_tokens` 和 `timeout`
- `classifier`：开销分类置信度阈值
- `diet`：餐顿类型和饮食抽取置信度阈值

`.env` 包含：

- `LLM_API_KEY`：必填，不能提交到版本控制的密钥

模型名、服务地址和推理参数统一在 `config.yaml` 的 `llm` 段配置；`.env` 只保存密钥。

分类配置会按 `config.yaml` 修改时间刷新，通常不需要重启 Streamlit。

## 技术栈

- UI：Streamlit
- LLM：LangChain + OpenAI-compatible API
- 数据库：SQLite（stdlib，无 ORM）
- 数据处理：Pandas
- 可视化：Plotly
