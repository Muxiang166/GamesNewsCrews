# Game\_News\_Intelligence\_System（计划）

## 1. 概要

在 `d:\PythonProjects\Games_News_Crew` 下初始化一个多智能体“游戏资讯情报系统”，以 CrewAI 的顺序流（Sequential Process）串联：

1. Research（DuckDuckGo 实时搜索）→ 2) Analysis（去重 + 真实性评估 + 趋势/情绪）→ 3) Editing（行业简报 Markdown）→ 4) Social（小红书/微博风格文案 + 配图提示词）。

交付物包含：`requirements.txt`、`config/agents.yaml`、`config/tasks.yaml`、`main.py`、`.env.example` 与必要的输出目录/样例输出文件（如 `outputs/`）。

## 2. 当前状态分析（基于环境探查）

* `d:\PythonProjects\Games_News_Crew` 目录当前为空（未发现既有代码/配置/示例）。

* 本地仓库内未发现你提到的 `stock_analysis` 示例代码可供“借鉴其逻辑”。因此“借鉴”将以 CrewAI 顺序流的通用结构来实现，并在实现阶段尽量保持可替换（后续你提供 stock\_analysis 后可进一步对齐细节）。

## 3. 关键需求与已确认决策

* 项目根目录：直接在 `d:\PythonProjects\Games_News_Crew` 生成结构。

* 交付范围：完整增强版（含更严格的去重/可信度评分、输出模板与日志）。

* 依赖策略：锁主版本（使用 `>=x,<x+1` 或等价约束）。

* LLM：DeepSeek（通过 `.env` 提供 `DEEPSEEK_API_KEY` 等配置）。

* 额外 Agent：增加“小红书/微博发布风格简报 + 图片提示词”能力；本阶段做到“生成文案 + 提示词”，不接入实际发布接口。

## 4. 方案设计（实现层面决策）

### 4.1 目录与文件结构（将要创建）

* `requirements.txt`

* `config/agents.yaml`

* `config/tasks.yaml`

* `main.py`

* `.env.example`

* `outputs/`（运行产物目录；可由 main.py 自动创建）

### 4.2 YAML 配置约定（agents.yaml / tasks.yaml）

你提供的参考仓库里（`crewAI-examples/crews/stock_analysis`）说明了 stock_analysis 的核心构成（main、agents、tasks、tools），但由于 GitHub 归档与页面渲染限制，这里无法稳定直接抓到 `main.py/stock_analysis_agents.py/stock_analysis_tasks.py` 的源码。因此本项目将以 **CrewAI 官方 Quickstart 文档所示的 YAML 字段**作为配置结构真值，并用 stock_analysis 的“多角色顺序流水”实现风格迁移到游戏资讯场景中。

**agents.yaml（对齐官方结构）**

* 顶层 key 就是 agent 名称（例如 `researcher`）
* 每个 agent 下包含：
  * `role`
  * `goal`
  * `backstory`

本阶段包含 4 个 agent key：

* `researcher`：资深游戏研究员（必须绑定 DuckDuckGoSearchRun 工具）

* `analyst`：行业分析师（去重、真实性评估、趋势/情绪）

* `editor`：主编（产出 Markdown 行业简报）

* `social_publisher`：社媒编辑（产出小红书/微博文案 + 配图提示词；不做真实发布）

**tasks.yaml（对齐官方结构）**

* 顶层 key 就是 task 名称（例如 `news_scoping`）
* 每个 task 下包含：
  * `description`
  * `expected_output`
  * `agent`（引用 agents.yaml 的 agent key）
  * `output_file`（可选）

包含 3 个核心任务（与你最初要求一致）：

* `news_scoping`：资讯搜寻

* `sentiment_trend_analysis`：情绪与趋势分析（含去重与真实性评估）

* `final_briefing_drafting`：最终简报起草

并在 `final_briefing_drafting` 之后追加一个社媒增强任务（agent 为 `social_publisher`），用于生成微博/小红书文案与配图提示词（作为“增强版输出”，保持主 3 任务结构稳定）。

### 4.3 顺序流（Sequential Process）数据流

1. `news_scoping`：

   * 输入：目标游戏名（默认示例：黑神话：悟空）、时间范围、关键词扩展（可通过命令行参数传入）

   * 行为：Researcher 通过 DuckDuckGoSearchRun 实时搜索；输出为“带来源的条目列表（标题/摘要/URL/发布时间/站点）”
2. `sentiment_trend_analysis`：

   * 输入：上一步条目列表

   * 行为：

     * 去重：URL 归一化 + 标题相似度/站点/时间窗口

     * 真实性评估：来源域名可信度启发式 + 多源交叉印证计数 + “明显转载/营销/未署名”等信号

     * 趋势/情绪：对高可信条目做主题聚类与情绪倾向概述（以 LLM 总结为主，保留引用链接）

   * 输出：结构化“情报要点”（去重后条目、可信度评分、关键趋势、风险提示）
3. `final_briefing_drafting`：

   * 输入：结构化情报要点

   * 行为：Editor 产出标准 Markdown（含：摘要、关键动态、趋势与影响、风险与不确定性、引用来源清单）

   * 输出：写入 `outputs/briefing.md`
4. 社媒增强（由 `social_publisher` 生成）：

   * 输入：briefing 核心要点

   * 输出：

     * `outputs/weibo.md`：微博风格（短、信息密度高、带话题/引用链接策略）

     * `outputs/xhs.md`：小红书风格（标题党但不夸张、分点、种草/讨论导向）

     * `outputs/image_prompts.md`：配图提示词（封面图/信息图/时间线图等）

## 5. 具体改动清单（文件级）

### 5.1 requirements.txt

目标：满足你指定的四个包，并采用“锁主版本”策略；同时补齐运行所需的最小依赖（如 `pyyaml`）。

计划内容（示例约束，最终以可安装为准）：

* `crewai>=1,<2`

* `langchain-community>=0.4,<0.5`

* `duckduckgo-search>=8,<9`

* `python-dotenv>=1,<2`

* `pyyaml>=6,<7`

备注：DuckDuckGo 的 Python 包在 PyPI 上提示已改名为 `ddgs`，但为满足你“必须使用 DuckDuckGoSearchRun 工具”的要求，仍保留 `duckduckgo-search` 作为依赖；如后续 LangChain 切换到 `ddgs`，再做兼容调整。

### 5.2 config/agents.yaml

目标：定义 4 个 agent（前三个为你最初要求，第四个为你追加的社媒+配图）。

要点：

* Researcher：明确工具能力为“实时搜索”，并在 main.py 中强制绑定 `DuckDuckGoSearchRun`
  * 为同时满足“必须使用 DuckDuckGoSearchRun”与“CrewAI tools 需要 BaseTool”两点，将用 `crewai.tools.BaseTool` 包装 LangChain 的 `DuckDuckGoSearchRun`，避免引入额外工具依赖包。

* Analyst：强调“去重、真实性评估、趋势/情绪”

* Editor：强调“输出 Markdown 行业简报”

* Social：输出两平台文案 + 图片提示词（不发帖）

### 5.3 config/tasks.yaml

目标：定义 3 个核心任务（与你最初要求一致）+ 1 个社媒增强任务（你新增需求），整体仍为顺序流。

### 5.4 main.py

目标：项目入口，读取 YAML，构造并运行 Crew（顺序流），并包含基础错误处理与可观测性输出。

包含能力：

* 加载 `.env`（开发态）与环境变量（生产态）

* 读取并校验 YAML Schema（字段缺失给出清晰报错）

* 初始化 LLM（DeepSeek）

* 初始化工具（Researcher 的 DuckDuckGoSearchRun）

* 组装 CrewAI 的 Agent/Task/Crew（Process.sequential）

* 捕获关键异常（配置缺失、网络/限流、LLM 调用失败、文件写入失败），输出可定位的错误信息并以非 0 退出码结束

* 将关键产物写入 `outputs/`（自动创建目录）

### 5.5 .env.example

目标：提供 DeepSeek 所需环境变量模板，并包含可选配置。

建议字段：

* `DEEPSEEK_API_KEY=`

* `DEEPSEEK_BASE_URL=`（如使用 OpenAI 兼容 endpoint）

* `DEEPSEEK_MODEL=`（例如 deepseek-chat / deepseek-reasoner 等，由你确认）

* `TARGET_GAME=`（默认搜索目标）

* `SEARCH_TIME_RANGE=`（例如 7d）

* `SEARCH_MAX_RESULTS=`（例如 20）

## 6. 验证与验收

### 6.1 本地环境初始化（Windows / PowerShell）

已验证可用的 Conda 环境方案（推荐）：

* Conda 版本：24.7.1
* 环境名：gamesnewscrew
* Python：3.11.15
* 环境位置：D:\Anaconda\envs\gamesnewscrew

可复制的终端步骤：

* 创建环境：
  * `conda create -n gamesnewscrew python=3.11 -y`
* 安装依赖（在项目根目录执行）：
  * `conda run -n gamesnewscrew python -m pip install -r requirements.txt`
* 校验关键依赖可导入：
  * `conda run -n gamesnewscrew python -c "import crewai, yaml, dotenv; from langchain_community.tools import DuckDuckGoSearchRun; print('imports_ok')"`
* 配置密钥：
  * 复制 `.env.example` 为 `.env` 并填写 `DEEPSEEK_API_KEY`
* 运行：
  * `conda run -n gamesnewscrew python main.py --game "黑神话：悟空"`

说明：在 Trae 的沙箱环境中执行 conda 可能出现“restricted / pkgs cache”相关提示，但本次已确认环境创建与依赖安装成功。

### 6.2 运行验证

* 通过一次真实查询验证顺序流全链路可运行：

  * Researcher 能返回包含 URL 的结果

  * Analyst 输出去重后条目数、可信度分布与趋势要点

  * Editor 生成 `outputs/briefing.md`

  * Social 生成 `outputs/weibo.md`、`outputs/xhs.md`、`outputs/image_prompts.md`

* 错误场景验证：

  * 未配置 `DEEPSEEK_API_KEY` → 程序给出明确提示并退出

  * DuckDuckGo 被限流/无结果 → 降级提示与可重试建议

## 7. 假设与后续需要你补充的信息

* 你已提供 `crewAI-examples/crews` 作为参考来源；本计划将以 CrewAI 官方 Quickstart 的 YAML 字段（role/goal/backstory 与 description/expected_output/agent/output_file）作为配置结构真值，并以 stock_analysis README 描述的“main + agents/tasks + tools + 顺序协作”作为实现风格参考。
