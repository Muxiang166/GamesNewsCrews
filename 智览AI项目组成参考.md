# 智览 AI 项目组成参考

来源：`智览AI项目组成参考.pdf`

抽取说明：本文由 PDF 文本抽取后整理为 Markdown。由于当前环境没有 Poppler 渲染工具，未做视觉级排版还原；本文件主要用于参考设计、架构分层、工具链和库选型，不作为 `Games_News_Crew` 的硬性路线约束。

## 1. 项目定位

原 PDF 描述的是一个面向金融、咨询、媒体行业的 `AgenticRAG Platform`，目标是把多源信息采集、去重聚类、深度摘要生成、每日简报推送串成自动化平台。

可参考之处：

- 它的业务对象是“新闻/研报/摘要”，与本项目的“游戏资讯智能体”同属信息采集、证据组织、内容生成类系统。
- 它强调 `LangGraph` 编排、`LangChain` 工具层、RAG 检索、前后端服务化、缓存和监控，这些都可以作为后续架构参考。
- 它偏金融研报，强依赖深度摘要、行业分析和 PDF 导出；本项目更偏 48 小时游戏热点、社交热度、流言分级、人工评分和图文平台内容。

## 2. 技术栈参考

PDF 中列出的主要技术栈：

| 层级 | 工具/库 | 参考用途 |
| --- | --- | --- |
| 工作流编排 | LangGraph | 有状态多 Agent 工作流编排 |
| LLM 工具层 | LangChain | LLM 调用链、Prompt 模板、文档处理 |
| 大模型 | Qwen3.7 Max | 长上下文生成与分析 |
| Embedding | Qwen3-Embedding | 文本向量化 |
| 检索 | Elasticsearch 8.x | 向量 kNN + BM25 混合搜索 |
| 缓存 | Redis | 热点缓存、任务去重、降级 |
| 后端 | FastAPI | REST API + WebSocket |
| 前端 | Nuxt 3 + Vue 3 | SSR/SSG、Composition API |
| 样式 | Tailwind CSS | 实用优先 CSS |
| 可视化 | ECharts | 数据看板、趋势图、聚类可视化 |
| 关系库 | MySQL | 关系型数据存储 |
| 采集 | NewsAPI + 爬虫 + RSS | 多源新闻采集 |

对本项目的初步取舍：

- 可优先参考：`FastAPI`、`Nuxt 3 + Vue 3`、`Tailwind CSS`、`ECharts`、`Redis`、`LangGraph`、`LangChain`。
- 短期替代：关系库可先用 SQLite，等服务化稳定后再评估 PostgreSQL/MySQL。
- 暂缓：Elasticsearch、HDBSCAN、Embedding 聚类、Celery、Nginx 全栈部署。它们适合数据量和服务化需求变大后再接入。

## 3. 总体架构参考

PDF 的整体架构：

```text
前端展示层：Nuxt 3 + Vue 3
  Dashboard / 研报中心 / 数据看板 / 配置管理 / 实时监控

API 网关层：FastAPI
  认证鉴权 / 请求路由 / 限流控制 / 参数校验

LangGraph 工作流编排层
  采集 Agent -> 去重 Agent -> 聚类 Agent -> 摘要 Agent -> 研报 Agent -> 审核 Agent -> 推送 Agent

数据与基础设施层
  Redis / Elasticsearch / MySQL / 文件存储
```

对本项目的对应关系：

```text
Nuxt 3 工作台
  Run 列表 / 阶段状态 / 候选池 / Story / 评分 / LLM Shadow 对比 / 用户通知

FastAPI 服务层
  启动 run / 查询 run / 读取 artifact / 写入人工评分 / 导出内容包

LangGraph 主流程
  SourcePlanner -> SearchCollector -> FetchDocuments -> Evidence/Verification
  -> ThemeReranker -> ContentQualityGate -> Review Pack

数据层
  JSON artifacts -> SQLite mirror -> Redis cache -> 后续向量库或搜索引擎
```

## 4. 工作流模块参考

PDF 中的 LangGraph 流程：

1. 多源采集 `Collect`
2. 数据预处理 `Preprocess`
3. 去重检测 `Dedup`
4. 语义聚类 `Cluster`
5. RAG 检索增强 `Retrieve`
6. 深度摘要生成 `Summarize`
7. 质量审核 `Review`
8. 研报组装 `Compose`
9. 格式导出 `Export`
10. 推送分发 `Dispatch`

本项目当前更适合的映射：

| PDF 模块 | 本项目映射 | 当前建议 |
| --- | --- | --- |
| Collect | `SearchCollector` / source parsers / social heat providers | 继续保留确定性采集为事实来源 |
| Preprocess | candidate filtering / theme split / document fetch | 已有基础，继续靠 artifact contract 固化 |
| Dedup | `CandidateDedup` / `StoryClusterer` | 先做明显重复，语义聚合后接 LLM/RAG |
| Cluster | story clustering / event timeline | 不急着上 HDBSCAN，先规则 + 人工/LLM 请求包 |
| Retrieve | `EvidenceRetriever` / SQLite FTS/BM25 | 适合进入 0.2.x |
| Summarize | MarkdownEditor / platform writer / LLM shadow | 先做辅助对比，不直接替代确定性产物 |
| Review | ContentQualityGate / human review / LLM shadow | 是 0.2.0 的重点 |
| Compose | briefing / material bundle / later layout manifest | 已有文本产物，排版继续暂缓 |
| Export | Markdown / later image/PDF | 暂缓到内容质量稳定后 |
| Dispatch | platform publishing | 继续作为发布前硬门，不进入 0.2.0 |

## 5. 采集模块参考

PDF 中的采集方式：

- NewsAPI 采集器：关键词、语言、时间范围过滤。
- 自定义爬虫：面向特定站点。
- RSS 订阅：主流媒体源订阅。
- PDF 解析：提取财报数据。
- 容错机制：单源失败自动重试。
- 数据模型：`RawArticle(source, title, content, url, published_at, author, language, topic_tags, raw_html)`。

对本项目的启发：

- 本项目应保留 `RawSource` / `SearchCandidate` / `Document` 三层，不要把原始抓取、候选和正文混成一个对象。
- FastAPI 服务化后，`RawArticle` 类似结构可以对应数据库里的 `raw_sources`、`candidates`、`documents`。
- Redis 可用于 URL 去重、短期页面缓存、同一 run 的任务去重，但事实记忆仍应进 SQLite/关系库。

## 6. 去重与聚类参考

PDF 的三层去重策略：

1. 精确去重：URL 哈希 + 标题哈希 + BloomFilter。
2. 近似去重：SimHash / MinHash。
3. 语义去重：Embedding 向量相似度。

本项目取舍：

- 0.2.0 继续优先确定性去重：URL 规范化、标题规范化、时间窗、来源、主题板块。
- SimHash / MinHash 可以作为后续轻量增强。
- Embedding 聚类和 HDBSCAN 暂缓，等长窗口历史库、人工样本和误删风险评估稳定后再接。
- LLM/RAG 适合处理“重复转载 vs 连续新细节”的边界样本，不适合第一版全量替代规则。

## 7. RAG 与摘要参考

PDF 的 RAG 流程：

1. Query 改写。
2. 向量检索 + BM25 多路召回 + 时间过滤。
3. Cross-Encoder 精排。
4. Top-K 片段与历史背景组装为 Prompt。
5. 大模型按模板生成深度摘要。

本项目取舍：

- 0.2.0 可体现“确定性产物 vs LLM 辅助产物”的差异，优先从 query compression、search relevance、editorial judgment 做 shadow。
- RAG v0 应继续使用 SQLite FTS/BM25 + metadata filter，先证明证据包可查、可引用、可回放。
- 向量库、Cross-Encoder 和复杂 rerank 暂缓，避免在候选质量和人工评分尚不稳定时扩大系统复杂度。

## 8. 前端参考

PDF 推荐的前端：

- Nuxt 3 + Vue 3
- Tailwind CSS
- ECharts
- Pinia + Vue Query
- WebSocket 实时通信
- ofetch API 客户端

可用于本项目的页面：

- Dashboard：最近 run、阶段分数、阻塞通知、候选数量、LLM 调用成本。
- 内容评审：展示 `content_review.md`、story、证据、平台草稿、人工评分。
- 阶段产物：按 `artifacts_by_stage` 浏览 JSON/Markdown。
- LLM 对比：同一批候选的 deterministic 输出 vs LLM shadow 输出。
- 来源健康：source health、collector errors、schema validation、用户通知。
- 后续：布局预览、图片渲染、发布草稿。

## 9. API 参考

PDF 提到的接口：

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/collect` | POST | 触发即时采集 |
| `/api/v1/topics` | GET/POST/DELETE | 管理监控主题 |
| `/api/v1/briefs` | GET | 获取历史日报列表 |
| `/api/v1/briefs/{date}` | GET | 获取指定日期日报 |
| `/api/v1/reports` | GET | 获取研报列表 |
| `/api/v1/clusters` | GET | 获取聚类结果 |
| `/api/v1/status` | GET | 系统运行状态 |
| `/api/v1/config` | GET/PUT | 系统配置管理 |

本项目服务化 MVP 可以改成：

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/runs` | GET | 列出运行记录 |
| `/api/v1/runs` | POST | 启动一次 LangGraph run |
| `/api/v1/runs/{run_id}` | GET | 查看 run manifest |
| `/api/v1/runs/{run_id}/events` | GET | 查看 run events |
| `/api/v1/runs/{run_id}/notifications` | GET | 查看用户通知 |
| `/api/v1/runs/{run_id}/artifacts` | GET | 查看 artifact index |
| `/api/v1/runs/{run_id}/artifacts/{artifact_key}` | GET | 读取指定 artifact |
| `/api/v1/runs/{run_id}/review` | POST | 写入人工评分和备注 |
| `/api/v1/shadow-tests` | POST | 对指定 run 执行 LLM shadow 小样本测试 |

## 10. 目录结构参考

PDF 的参考目录：

```text
backend/
  app/
    main.py
    config.py
    agents/
    collectors/
    processors/
    rag/
    generators/
    exporters/
    dispatchers/
    cache/
    scheduler/
    models/
    api/
frontend/
  pages/
  layouts/
  components/
  composables/
  stores/
  plugins/
  utils/
  types/
docker-compose.yaml
.env.example
```

本项目后续更合适的目录：

```text
LangGraph/
  src/games_news_agent/
    collectors/
    persistence/
    retrieval.py
    llm_shadow.py
    langchain_adapter.py
services/
  api/        # FastAPI
  web/        # Nuxt 3
docs/
outputs/
```

## 11. 关键风险与解决方案参考

PDF 提到的难点：

- 长文本处理：分段、Map-Reduce、RAG 分层检索。
- 摘要质量：事实核查、引用溯源、结构化模板。
- 工作流可靠性：LangGraph checkpointing、断点恢复、外部 API 重试。
- 服务稳定性：Redis 缓存降级、异步执行、进度回调、超时控制。

对本项目的下一步启发：

- 先不要把服务化做成完整生产系统，先做内部工作台。
- 先暴露 run trace、artifact index、schema validation、user notifications。
- LLM 只做 shadow 对比，不能直接改事实链路。
- Redis/Celery/Nginx/Docker Compose 可以写进后续计划，但 0.2.0 不必马上实现。

## 12. 对 0.2.0 的直接参考

0.2.0 可以定义成：

> 一个可运行、可复盘、可人工评分的游戏资讯智能体版本。它能输出确定性工程产物，也能在显式开关下生成 LLM 辅助 shadow 产物，用于比较 LLM 是否改善 query、相关性判断、编辑判断和内容质量解释。

建议包含：

- 确定性主流程：采集、候选分流、正文取证、证据包、去重、主题精排、内容质量报告。
- LLM shadow：query compression、search relevance、editorial judgment、story cluster review。
- 追踪：run manifest、run events、artifact index、schema validation、user notifications。
- 评审：content review、human review template、LLM shadow 对比报告。
- 服务化准备：FastAPI/Nuxt3 只先做工作台，不做自动发布。
