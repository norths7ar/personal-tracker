# expense-tracker

基于 Streamlit + LLM 的个人记账工具，供本地 Windows 使用。

## 功能

- **记一笔**：记录支出、收入、迁移三类账目
  - 支出自动调用 LLM（DeepSeek）分类；置信度低时弹出候选项确认；识别到未知类别时提示手动确认
  - 收入从配置文件选择分类
  - 迁移（理财转账、信用卡还款等）直接存入，不参与收支计算
- **报表**：按周 / 月 / 年查看收支结余、日均、与上期对比、分类明细
- **流水**：查看全部记录，支持按类型筛选和关键词搜索，可编辑或删除任意记录

## 项目结构

```
expense-tracker/
├── app.py              # 入口，定义导航页面
├── config.yaml         # 分类配置（支出 / 收入 / 迁移）和 LLM 参数
├── .env                # API 密钥（不进版本控制）
├── .env.example        # 密钥配置示例
├── requirements.txt    # Python 依赖
├── core/
│   ├── db.py           # SQLite 操作（纯 stdlib）
│   ├── llm.py          # LLM 调用封装（LangChain + DeepSeek）
│   └── classifier.py   # 分类逻辑，输出 status 驱动页面流程
├── pages/
│   ├── 1_记账.py       # 记一笔
│   ├── 2_分析.py       # 报表
│   └── 3_记录.py       # 流水
└── data/
    └── expenses.db     # SQLite 数据库（不进版本控制）
```

## 快速开始

```bash
# 1. 创建并激活 conda 环境
conda create -n expense-tracker python=3.12
conda activate expense-tracker

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API 密钥
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 4. 启动
streamlit run app.py
```

## 配置说明

`config.yaml` 分三段：

- `支出`：LLM 分类用的类别树，格式为 `主类别: [子类别列表]`；子类别为空列表 `[]` 时代表无子类
- `收入`：收入分类，记账时手动选择
- `迁移`：迁移分类，不参与收支结余计算

修改分类后重启 Streamlit 生效（`@st.cache_resource` 不会热重载）。

## 技术栈

- UI：Streamlit
- LLM：LangChain + DeepSeek API（兼容 OpenAI 格式）
- 数据库：SQLite（stdlib，无 ORM）
- 数据处理：Pandas
- 可视化：Plotly
