# 全局 Issues 与 Harness 索引

本文件是项目的长期 issue 总表。阶段是路线安排，issue 按功能层归属；任何阶段都可以回头修改前面功能层的 issue。每个 issue 必须绑定：功能层、输入输出 artifact、harness 用例、通知策略和进入主流程条件。

## 统一规则

- Issue ID 使用功能层前缀，而不是阶段编号。
- Harness 放在 `LangGraph/harness/<layer>/`，自动测试放在 `LangGraph/tests/`。
- 每次实现前至少有一个用例设想：输入、期望输出、失败/异常行为。
- LLM/Agent 只能写结构化结果或建议，不直接改最终事实。
- 任何无法自动处理的异常必须写入 `user_notifications.json`，同时进入 `run_events.jsonl`，以便未来网页端显示。

## 2026-06-16 实现审计状态

- 测试通过不等于功能已进入主流程。后续文档必须区分：`main_flow`（默认链路执行）、`flagged_node`（CLI 开关后执行）、`shadow_mode`（只写建议/请求包）、`offline_tool`（离线脚本或库函数）、`harness_only`（仅 fixture/单测约束）。
- 本轮确认：`SearchIntelligence`、`SourceRecoveryAgent`、`StoryClusterReviewAgent`、`EvidenceRetriever`、`EventStore` 均已有 MVP 或 scaffold，但多数仍是 gated/shadow/offline；它们不能被描述为已经由 LLM/RAG/Agent 接管事实判断。
- 本轮修正：`SourceRecoveryAgent` 新增 `SourceRecoveryPolicy`，`search_intelligence.py` 新增 `SearchRelevancePolicy` 和搜索结果级 `result_published_at/result_metadata` 参数，避免恢复阈值、相关性阈值和结果发布时间只能靠硬编码或把字段塞进原候选。

## Harness 放置

```text
LangGraph/harness/
  run_trace/
  source_collection/
  search_expansion/
  candidate_filtering/
  evidence_retrieval/
  discussion_heat/
  story_clustering/
  claim_verification/
  story_selection/
  content_quality/
  layout_render/
  operations/
  service_workbench/
  memory_sql/
  prompt_management/
  agent_contracts/
  langchain_adapter/
  shadow_tasks/
```

单元测试也算 harness，适合固定单个函数或节点合同；JSON fixture 适合跨节点 replay；真实 `outputs/langgraph/<run>/artifacts_by_stage/` 适合人工和 Agent 复盘。

### Harness Fixtures 已创建清单

以下 JSON fixture 已在本工作流中创建，覆盖所有功能层：

- `LangGraph/harness/run_trace/H-RUN-001-dry-run-manifest.json`
- `LangGraph/harness/run_trace/H-RUN-002-node-exception.json`
- `LangGraph/harness/run_trace/H-RUN-003-artifact-index.json`
- `LangGraph/harness/run_trace/H-RUN-004-schema-validation.json`
- `LangGraph/harness/source_collection/H-COL-001-retry-success.json`
- `LangGraph/harness/source_collection/H-COL-002-http404.json`
- `LangGraph/harness/source_collection/H-COL-003-http500-exhausted.json`
- `LangGraph/harness/source_collection/H-COL-004-recovery-suggestion.json`
- `LangGraph/harness/search_expansion/H-SRC-001-query-compression.json`
- `LangGraph/harness/search_expansion/H-SRC-002-relevance-classification.json`
- `LangGraph/harness/candidate_filtering/H-FIL-001-theme-split.json`
- `LangGraph/harness/candidate_filtering/H-FIL-002-non-game-filter.json`
- `LangGraph/harness/evidence_retrieval/H-EVI-001-evidence-chunks.json`
- `LangGraph/harness/evidence_retrieval/H-EVI-002-evidence-pack.json`
- `LangGraph/harness/discussion_heat/H-HEAT-001-unified-observations.json`
- `LangGraph/harness/discussion_heat/H-HEAT-002-old-discussion.json`
- `LangGraph/harness/story_clustering/H-CLU-001-dedup-merge.json`
- `LangGraph/harness/story_clustering/H-CLU-002-followup-not-duplicate.json`
- `LangGraph/harness/claim_verification/H-VER-001-fact-vs-rumor.json`
- `LangGraph/harness/claim_verification/H-VER-002-rumor-confirmed.json`
- `LangGraph/harness/story_selection/H-RANK-001-per-section-selection.json`
- `LangGraph/harness/story_selection/H-RANK-002-core-game-priority.json`
- `LangGraph/harness/content_quality/H-GEN-001-rumor-labeling.json`
- `LangGraph/harness/content_quality/H-GEN-002-quality-report.json`
- `LangGraph/harness/layout_render/H-LAY-001-missing-image.json`
- `LangGraph/harness/operations/H-OPS-001-blocking-stops-publish.json`
- `LangGraph/harness/service_workbench/H-SVC-001-run-list-api.json`
- `LangGraph/harness/service_workbench/H-SVC-002-artifact-stage-browser.json`
- `LangGraph/harness/service_workbench/H-SVC-003-human-review-save.json`
- `LangGraph/harness/service_workbench/H-SVC-004-readonly-guard.json`
- `LangGraph/harness/memory_sql/H-MEM-001-ingest-parity.json`
- `LangGraph/harness/memory_sql/H-MEM-002-query-differentiate.json`
- `LangGraph/harness/memory_sql/H-MEM-003-agent-db-query.json`
- `LangGraph/harness/prompt_management/H-PRM-001-prompt-registry-valid.json`
- `LangGraph/harness/prompt_management/H-PRM-002-prompt-output-parse-failure.json`
- `LangGraph/harness/agent_contracts/H-AG-001-bounded-decision.json`
- `LangGraph/harness/agent_contracts/H-AG-002-no-suitable-tool.json`
- `LangGraph/harness/langchain_adapter/H-LCA-001-tool-invoke-retry-output.json`
- `LangGraph/harness/shadow_tasks/H-SHD-001-shadow-results-failures.json`

共计 39 个 fixture，覆盖 run_trace、source_collection、search_expansion、candidate_filtering、evidence_retrieval、discussion_heat、story_clustering、claim_verification、story_selection、content_quality、layout_render、operations、service_workbench、memory_sql、prompt_management、agent_contracts、langchain_adapter、shadow_tasks 全部 18 个功能层的 harness 目录。

## 功能能力描述与 Harness 参考

这一节用于后续 README、网页端文档和测试用例设计。每个功能层都应能写成"用户可以通过 X 来 Y"，并能回链到可回放 artifact 或 harness。

| 功能层 | 用户能力描述 | 主要入口/产物 | Harness 参考 | 当前状态 |
| --- | --- | --- | --- | --- |
| RUN | 用户可以通过一次 CLI run 看到本轮执行了哪些节点、产出了哪些文件、哪里失败以及下一步需要人工做什么。 | `LangGraph/main.py`、`run_manifest.json`、`run_events.jsonl`、`user_notifications.json` | `H-RUN-001/002/003/004` | main_flow MVP |
| COL | 用户可以通过 sources 配置和运行参数控制抓取范围，并在候选少、时间戳缺失或来源异常时看到恢复建议。 | `LangGraph/config/sources.yaml`、`raw_sources.jsonl`、`collector_errors.json`、`source_recovery_plan.json` | `H-COL-001/002/003/004` | main_flow + flagged recovery |
| SRC | 用户可以通过搜索拓展把候选标题压缩成短 query，并判断搜索结果是否同事件、同游戏、仍在时间窗内。 | `search_intelligence.py`、`search_expansion_requests/results`、`llm_search_expansion_*` | `H-SRC-001/002` | deterministic MVP + LLM shadow planned |
| FIL | 用户可以查看候选如何进入索尼、任天堂、微软、PC、补充板块，以及哪些非游戏内容被拒绝。 | `theme_candidate_pool.json`、`rejected_candidates.json`、`source_theme_counts.json` | `H-FIL-001/002` | main_flow MVP |
| EVI | 用户可以为 claim/story 检索证据包，看到引用 chunk、来源 URL、时间和缺失说明。 | `evidence_chunks.json`、`context_packs.json`、`retrieved_evidence_packs.json` | `H-EVI-001/002` | flagged_node/offline MVP |
| HEAT | 用户可以用公开社交搜索观察某条资讯是否在游戏语境里被讨论，并把弱相关结果送入语义复核。 | `discussion_probe_requests.json`、`social_heat_observations.json`、`semantic_relevance_requests.json` | `H-HEAT-001/002` | main_flow observations + relevance shadow |
| CLU | 用户可以看到明显重复新闻被合并，连续事件新细节被保留，并把模糊聚合送入人工/LLM 复核。 | `story_clusters.json`、`event_timelines.json`、`dedup_semantic_review_requests.json` | `H-CLU-001/002` | main_flow MVP + review scaffold |
| VER | 用户可以区分事实、证据支持、流言、冲突和待人工复核，并避免因果说法被写成确定结论。 | `claims.json`、`claim_verifications.json`、`llm_verification_requests/results` | `H-VER-001/002` | main_flow rules + LLM optional |
| RANK | 用户可以按每个主题板块分别选出最多 10 条 story，并解释游戏本体新闻为何优先于泛讨论。 | `stories.json`、`theme_sections.json`、`source_dominance_audit.json` | `H-RANK-001/002` | main_flow MVP |
| GEN | 用户可以得到可人工评分的 Markdown 简报、平台草稿和内容质量报告，而不是直接进入排版发布。 | `briefing.md`、`platform_posts.json`、`content_quality_report.json`、`content_review.md` | `H-GEN-001/002` | main_flow MVP |
| LAY | 用户未来可以把已验证内容和真实素材排成微博长图/小红书轮播/Bilibili 图文，不用 LLM 生图补事实。 | `layout_manifest.json`、`render_queue.json` | `H-LAY-001` | deferred scaffold |
| OPS | 用户未来可以在发布前看到 checklist、blocking 通知和平台草稿状态，并人工确认后再发。 | `user_notifications.json`、`platform_posts.json`、publish status fields | `H-OPS-001` | scaffold/deferred |
| SVC | 用户可以在内部工作台查看 run、阶段产物、通知、质量旗标、LLM shadow 对比和人工评分入口，而不是翻输出目录。 | FastAPI API、Nuxt3 workbench、`agent_query.py`、`human_reviews` | `H-SVC-001/002/003/004` | **implemented** (2026-06-17, 47/47 tests) |
| MEM | 用户可以把一次运行的 JSON artifact 镜像到 SQLite，并通过只读白名单查询候选、story、平台草稿、通知、质量旗标和历史事件关系。 | `sqlite_mirror.py`、`agent_query.py`、`event_store.py`、`event_store.db` | `H-MEM-001/002/003` | offline MVP |
| AG | 用户未来可以让受限 Agent 读取诊断 artifact，在白名单工具中选择恢复、复核或请求人工动作。 | `agent_contracts.py`、`source_recovery_agent.py`、`story_cluster_review_agent.py` | `H-AG-001/002` | scaffold/shadow |
| PRM | 用户/开发者可以通过 prompt registry 管理 prompt 文件、版本、输入输出、fallback 和 harness，避免 LLM 节点各自散落。 | `LangGraph/prompts/README.md`、`prompt_registry.json` | `H-PRM-001/002` | docs/contract MVP |
| LCA | 开发者可以把 Fetch/Search/SocialHeat/EvidenceRetriever 包成标准化 LangChain tool/Runnable，复用 schema、retry、batch 和 structured output parser。 | `langchain_adapter.py`、`tool_registry.json` | `H-LCA-001` | MVP v0 |
| SHD | 用户/开发者可以通过 LLM 阴影任务在小样本上获取建议，而不让 LLM 直接修改主流程的事实或排序。 | `shadow_results.json`、`shadow_failures.json`、`shadow_review_pack.json` | `H-SHD-001` | MVP v0 |

## 层级目标与验收标准

这一节定义"每个功能层完成后应该达到什么结果"。后续新增测试时，优先从这里取验收目标，而不是只断言脚本能跑完。

| 功能层 | 目标结果 | 最低验收标准 | 测试焦点 |
| --- | --- | --- | --- |
| RUN | 一次运行可以被完整复盘，用户知道运行状态、产物位置、失败原因和下一步动作。 | 每次 run 都生成 manifest、events、notifications；每个关键 artifact 有路径、大小、hash、schema_version、record_count；阻塞问题进入 notification。 | dry-run/live-run trace 完整性；异常节点是否阻断并通知；artifact index 是否能定位文件；schema registry 校验全部 artifact 类型。 |
| COL | 来源采集稳定、可解释、可恢复，候选少时能区分网络失败、入口错误、解析失败、时间戳缺失和来源本身低产。 | transient 错误有限重试；4xx 不盲重试；collector_errors 保留 attempts；source_recovery_plan 解释低产原因并给出白名单建议。 | retry budget；错误分类；source/theme count；parser contract；恢复建议不新增事实。 |
| SRC | 搜索拓展能补足固定源缺口，同时不把旧闻、标题党、相似但无关内容误当热点。 | query 1-3 条、短且不发明实体；每个搜索结果有 same_event/same_game/window/clickbait/old_news 判断；LLM 失败走 fallback。 | query compression 精度；结果时间窗；同游戏不同事件；旧闻/转载/营销号过滤。 |
| FIL | 候选在进入昂贵取证前完成时间窗、主题、类型和拒绝原因分流。 | 五个板块都有独立候选池；非游戏/泛娱乐/泛科技不进入核心板块；被拒候选必须有 reject_reason。 | 48h hard gate；theme carryover；candidate_type gate；underfilled section fill。 |
| EVI | 每条可发布 claim/story 都有可追踪证据包，证据只来自已观察材料。 | evidence chunk 有 URL/source/time/quote；retrieved pack 引用 chunk_id；无正文或相似证据只能标为参考，不可写入确定性 evidence。 | chunk metadata；BM25/FTS filter；claim-level evidence pack；缺证据边界。 |
| HEAT | 热度只证明"正在被讨论"，不证明事实；社交结果必须经过相关性门。 | observation 统一结构；平台 blocked/error 可诊断；same_game 但 not same_event 的结果不直接加热度分。 | provider contract；regional routing；old discussion；semantic review request 触发。 |
| CLU | 明显重复被合并，连续事件新 detail 被保留，模糊关系进入复核。 | 同 URL/轻改标题不重复占位；同游戏新设定/后续官宣不误删；semantic_review_requests 保留待判样本。 | duplicate merge；follow-up not duplicate；event timeline；historical duplicate scaffold。 |
| VER | 事实、流言、因果推断、冲突证据和人工复核状态清晰分开。 | 缺证据不得标为事实；流言保留外显标签；因果说法拆成事实与推断；冲突进入 conflict/manual_review。 | rumor tier；causal guard；evidence support score；LLM verifier fallback。 |
| RANK | 每个主题板块按内容价值、热度、证据、来源多样性分别精排，而不是全局一锅端。 | 每板块最多 10 条最终 story；游戏本体更新优先于低价值泛讨论；单源支配有 audit；排序理由可复盘。 | per-section final limit；core game policy；source dominance；low-value story 下沉。 |
| GEN | 生成内容可人工评审，证据、可信度、素材状态和风险标签可读。 | briefing/platform_posts/content_review 都引用 story/claim/evidence id；流言外显标签；quality gate 给出 score/gate/readiness。 | rumor labeling；quality report；平台草稿不新增事实；content_review 是否可评分。 |
| LAY | 已验证内容能被转为可渲染版面，缺素材时留空标注，不用 LLM 补图。 | layout_manifest 只引用真实素材或 manual_fill_required；render_queue 不凭空生成资产；平台尺寸和内容块分开。 | missing image placeholder；素材引用；平台画布约束；render artifact 可回放。 |
| OPS | 发布前必须经过状态、通知、平台限制和人工确认门。 | blocking notification 时不发布；平台文案默认 draft；story 默认 unpublished；发布动作可追踪。 | publish lifecycle；blocking stops publish；platform adapter approval gate。 |
| SVC | 内部工作台能把一次 run 从“目录里的文件”变成可浏览、可评分、可比较、可通知的产品界面。 | API 默认只读；run 列表、stage artifact、notifications、quality flags、shadow report、content review 可访问；人工评分只写 review 记录，不改事实产物。 | API schema；artifact path traversal guard；human review 保存；shadow/确定性对比；通知状态展示。 |
| MEM | JSON artifact 可镜像为长期可查的事件/证据/发布状态数据库。 | SQLite 可查询 raw/intermediate/final/publish 状态；同 URL 保留 first_seen/last_seen；事件、游戏、新闻关系可查。 | ingest parity；idempotency；event store links；historical import；query differentiate。 |
| AG | Agent 只在边界明确时选择白名单工具或请求人工，不接管事实链路。 | AgentDecision/ToolResult 结构化；无合适工具时 needs_user_action；Agent 不新增 URL/事实/证据。 | bounded action space；no suitable tool；source recovery decision；story cluster review suggestion。 |
| PRM | Prompt 像接口一样被登记、版本化、校验和回退。 | 每个 prompt 有 registry entry；文件存在；输入输出/fallback/harness 明确；parse/schema 失败只写 failures 和 notification。 | registry validity；prompt file coverage；parse failure；prompt version trace。 |
| LCA | Fetch/Search/SocialHeat/EvidenceRetriever 被包成标准化 LangChain tool/Runnable，可独立测试、可复用。 | 每个 tool 有 input/output schema、retry policy、batch 支持；structured output parser 能处理异常输出；ToolResult 包含 ok/error_type/suggested_actions。 | tool invoke/retry/batch；schema 校验；ToolResult 结构一致性；parser fallback。 |
| SHD | LLM 阴影任务只在小样本上输出建议和评审包，不修改主流程的事实和排序。 | shadow run 产生 results.json 和 failures.json；不修改 main artifacts；LLM 输出不直接写入 story/claim/ranking/publish。 | shadow 输出结构；main artifact 不可变性；failure 回退；小样本代表性。 |

阶段升级规则：

- 一个功能层从 `harness_only/shadow/offline` 升级为 `flagged_node` 前，必须至少有一个正向、一个失败、一个边界样本。
- 一个功能层从 `flagged_node` 升级为 `main_flow` 前，必须在真实或长窗口 replay 中证明不会降低上游精度、不会污染事实链路，并能通过 content review 解释结果。
- LLM/Agent 层的测试必须额外断言"不新增事实、不新增 URL、不直接改发布状态"。

## RUN：运行追踪与用户通知

目标：让每次运行可追踪、可回放、可解释，并能把未知问题通知用户。

### 目标结果

一次运行可以被完整复盘，用户知道运行状态、产物位置、失败原因和下一步动作。

### 最低验收标准

每次 run 都生成 manifest、events、notifications；每个关键 artifact 有路径、大小、hash、schema_version、record_count；阻塞问题进入 notification。

Issues:

- `RUN-001 RunTrace v0`：输出 `run_manifest.json`、`run_events.jsonl`、`user_notifications.json`。
- `RUN-002 Artifact Index`：记录 artifact_key、stage、schema_version、record_count、size_bytes、sha256。
- `RUN-005 ArtifactSchemaRegistry v0`：为关键 artifact 定义 schema_version、最低字段检查和失败通知，避免后续 SQL/RAG 读到半结构化文件。
- `RUN-003 UserNotification Contract`：所有无法自动恢复的问题都写成可 UI 展示的结构化通知。
- `RUN-004 LangGraph Recovery Edge`：后续把 blocking notification 连接到 human review / retry / recovery branch。
- `RUN-006 Non-blocking Warning Notifications`：source_broken、needs_fill、expected artifact missing、LLM shadow 高 fallback rate 等不阻塞主流程的问题，也要写入 warning notification，供 CLI、工作台和 Agent 读取。

Harness:

- `H-RUN-001`：dry-run 完整运行后，必须生成 manifest、events、notifications。
- `H-RUN-002`：模拟节点异常，必须生成 blocking notification，并保留错误类型和建议动作。
- `H-RUN-003`：artifact 写入后，manifest 能索引已有文件的 size/hash。
- `H-RUN-004`：dry-run 输出通过全部 11 种 artifact 类型的 schema 校验。

当前状态：`RUN-001` 已完成 MVP：CLI dry-run/live-run 结束后会写出 `run_manifest.json`、`run_events.jsonl`、`user_notifications.json`，并把它们复制到 `artifacts_by_stage/run_trace/`。
`RUN-002` MVP complete：`artifact_index` 现在记录 `schema_version` 和 `record_count`，每个 artifact 写入后自动更新索引条目。
`RUN-005` MVP complete v0：`ArtifactSchemaRegistry` 已为关键 JSON artifact 定义最低字段检查和失败通知；当前只校验已登记且可解析的 JSON 合同，跳过 `.jsonl`、Markdown 和未登记可选 artifact，避免产生假阳性。schema validation 之后会重新写回 `run_manifest.json` 与 `user_notifications.json`，便于后续 FastAPI/Nuxt 工作台读取。
`RUN-003` MVP complete：`user_notification_contract.py` 定义了结构化通知模式，包含校验函数 `validate_notification()` 确保所有字段符合合同。
`RUN-004` MVP complete：`ContentQualityGate` conditional edge 在质量得分低于阈值时阻断 run，写入 blocking notification 并跳过后续发布阶段。
`RUN-006` complete v0：`v020_ultracode_verify` 新增 `run_notifications.py`，在每次 run 后从 `source_health.json`（source_broken/needs_fill）、`shadow_run_report.json`（高 fallback rate）和 expected artifact 缺失检查生成 warning notification。`run.py` 在 shadow pipeline 后调用 `build_all_run_warnings` 并 re-write `user_notifications.json`。

## COL：来源规划、爬取与解析

目标：稳定从权威媒体、官方源、社交属性平台和未来浏览器探针中获得原始候选。

Issues:

- `COL-001 HttpFetcher Retry`：对 timeout、connection reset、DNS/SSL transient、HTTP 429、HTTP 5xx 做有限重试。
- `COL-002 Collector Error Propagation`：把 fetch attempts 透传到 `raw_sources.jsonl` 与 `collector_errors.json`。
- `COL-003 Site Parser Contract`：每个站点解析器声明入口、分页、时间戳来源、停止条件和失败类型。
- `COL-004 Source Recovery Suggestion`：当爬取数量异常少、结构变化或入口失效时，给出可审计恢复建议。
- `COL-005 Browser Probe Adapter`：确定性方法不足时，预留浏览器探针接口，不直接让 LLM 编造爬取结果。

Harness:

- `H-COL-001`：前两次 `URLError("timed out")`，第三次成功，期望 `attempts=3` 且最终 `ok=true`。
- `H-COL-002`：HTTP 404 只尝试一次，期望 `retryable=false`。
- `H-COL-003`：HTTP 500 尝试到预算耗尽，collector error 中保留 attempts。
- `H-COL-004`：某站点 48h 候选异常少时，输出 recovery suggestion 而不是静默通过。

当前状态：`COL-001` 与 `COL-002` 已完成 MVP；source-level cooldown/fuse、browser probe 仍后置。
`COL-003` MVP complete：`site_parser_contract.py` 为每个站点解析器声明入口、分页、时间戳来源、停止条件和失败类型；支持从 YAML 配置自动生成解析器合同。
`COL-004` MVP complete：`source_recovery_suggestion.py` 在爬取数量异常少、结构变化或入口失效时生成可审计恢复建议，包含 `diagnostics` 字段供人工复核。

## SRC：搜索拓展与候选发现

目标：在固定源不足时，低频、可解释地拓展搜索，不用硬堆关键词。

Issues:

- `SRC-001 Query Compression Shadow`：LLM 将标题/摘要压缩成 1-3 个短社媒 query。
- `SRC-002 Result Relevance Classification`：LLM/规则判断搜索结果是否同事件、同游戏、仍在 48h 内有效。
- `SRC-003 Event Burst Search`：发布会/游戏节期间允许新作/新内容突破日常数量限制，但必须保留来源和热度证据。
- `SRC-004 Fallback Search`：LLM 失败、超时或格式错误时保留原关键词搜索。

Harness:

- `H-SRC-001`：长标题生成短 query，不允许新增不存在的平台、游戏名或事实。
- `H-SRC-002`：旧闻、标题党、同事件转载、相似无关事件各一条，期望分类稳定。

当前状态：`SRC-001`/`SRC-002`/`SRC-004` MVP complete v0：`search_intelligence.py` 提供确定性 query 压缩、相关性分类和 fallback 搜索，不依赖 LLM 即可运行核心搜索拓展逻辑。

## FIL：候选过滤、分类与板块拆分

目标：从原始候选拆出索尼、任天堂、微软、PC、补充板块，并保留被拒原因。

### 目标结果

候选在进入昂贵取证前完成时间窗、主题、类型和拒绝原因分流。

### 最低验收标准

五个板块都有独立候选池；非游戏/泛娱乐/泛科技不进入核心板块；被拒候选必须有 reject_reason。

Issues:

- `FIL-001 TimeWindow Gate`：默认集中 48h，晚发复述降权或拒绝。
- `FIL-002 Candidate Type Gate`：区分主新闻、流言、平台价格、硬件、攻略、折扣、泛科技、梗图。
- `FIL-003 Theme Section Carryover`：板块意图一路传到 story，避免后续排序丢失来源板块语义。
- `FIL-004 Underfilled Section Fill`：某板块未达上限时按板块内排名补足，而不是被其他板块挤掉。

Harness:

- `H-FIL-001`：同一批候选按五个板块拆分，每板块最多 20 个候选进入后续评估。
- `H-FIL-002`：非游戏但高讨论内容只能进补充或待审，不进入核心板块。

当前状态：`FIL-004` MVP complete：underfilled section fill 逻辑从 supplemental/backfill 池中补足板块至上限，不被其他板块挤掉。

## EVI：正文抓取、证据包与 RAG

目标：把候选变成可验证证据包。RAG 只负责找证据，不直接判断事实真假。

Issues:

- `EVI-001 Document Fetch Budget`：正文抓取预算按板块分配，不再被全局上限过早截断。
- `EVI-002 Evidence Chunk Contract`：每个 chunk 保留 URL、source_id、title、published_at、quote、credibility_hint。
- `EVI-003 EvidenceRetriever v1`：SQLite FTS/BM25 + metadata filter 返回 evidence packs。
- `EVI-004 Vector Retrieval Adapter`：跨语言和历史相似事件需求稳定后接向量库。

Harness:

- `H-EVI-001`：给定候选和模拟正文，输出可追溯 evidence chunks。
- `H-EVI-002`：给定 claim 和 SQLite fixture，返回带 chunk_id/source/url 的 evidence pack。

当前状态：`EVI-003` MVP complete v0：`SQLiteFTS`/`BM25` evidence retriever 已实现，支持 metadata filter 和 relevance scoring，可返回结构化 evidence packs。

## HEAT：社交热度与讨论证据

目标：用 Bilibili、Steam、小黑盒、贴吧、微博、Reddit 等平台验证"是否正在被讨论"，不证明事实本身。

### 目标结果

热度只证明"正在被讨论"，不证明事实；社交结果必须经过相关性门。

### 最低验收标准

observation 统一结构；平台 blocked/error 可诊断；same_game 但 not same_event 的结果不直接加热度分。

Issues:

- `HEAT-001 SocialHeatProvider Contract`：各平台输出统一 observations。
- `HEAT-002 Regional Heat Routing`：按来源语言/地区选择验证平台。
- `HEAT-003 Semantic Relevance Review`：热度结果可能同游戏不同事件时，进入 LLM/人工语义核查。
- `HEAT-004 Login Boundary`：优先不登录公共搜索；登录能力作为后续合规设计，不进入当前主流程。

Harness:

- `H-HEAT-001`：同一候选在 Bilibili/Steam 返回观测，输出统一结构。
- `H-HEAT-002`：同游戏旧讨论不得被当作当前 48h 热度。

当前状态：`HEAT-001`/`HEAT-004` MVP complete：`social_heat.py` 定义统一 observation/contract，`discussion_probe_provider.py` 与相关测试覆盖公开搜索 provider 的最小接入；login boundary 明确分离为公共搜索优先、登录能力作为后续合规设计。注意：这仍是低频公开搜索与结构化观测层，不等于 Bilibili/微博/小黑盒等平台热度已完整接入。

## CLU：去重、连续事件与故事聚合

目标：去除明显重复新闻，同时保留连续事件的新 detail。

### 目标结果

明显重复被合并，连续事件新 detail 被保留，模糊关系进入复核。

### 最低验收标准

同 URL/轻改标题不重复占位；同游戏新设定/后续官宣不误删；semantic_review_requests 保留待判样本。

Issues:

- `CLU-001 CandidateDedup v1`：URL、标题规范化、实体重合、发布时间接近的保守去重。
- `CLU-002 Semantic Review Requests`：规则无法判断重复/后续时写入 LLM/人工请求包。
- `CLU-003 Event Timeline`：发布会/直播期间把连续新细节聚成同一事件时间线。
- `CLU-004 Historical Duplicate Check`：通过 SQL/RAG 判断旧闻复读、后续更新、同游戏不同事件。

Harness:

- `H-CLU-001`：同 URL/同标题轻改合并，但多来源证据保留。
- `H-CLU-002`：发售日公布后又公布角色设定，不能误删为重复。

当前状态：`CLU-003`/`CLU-004` MVP scaffold v0：`event_timeline.py` 提供确定性事件时间线与历史重复判断函数，能够识别明显重复、旧闻复读和连续新细节的候选关系；SQL/RAG 级历史查重仍在 `persistence/event_store.py` 与后续 retriever 设计中推进，暂未形成独立 `historical_duplicate.py` 模块。

## VER：Claim、事实核查与流言分级

目标：区分事实、流言、因果推断和冲突证据。

Issues:

- `VER-001 Claim Extraction`：从 context pack 输出结构化 claim。
- `VER-002 Evidence Verification`：规则/LLM/人工基于证据输出 verified、likely、rumor、conflict、reject。
- `VER-003 Rumor Tiering`：外部展示简化为 `[流言][未验证/待验证/可信爆料]`。
- `VER-004 Causal Claim Guard`：DEI、亏损、涨价等因果说法必须拆分事实与推断。

Harness:

- `H-VER-001`：有证据的普通事实至少 likely；缺证据的流言不得写成事实。
- `H-VER-002`：流言被官方确认/辟谣时，能关联旧流言和新事实。

当前状态：`VER-003`/`VER-004` MVP complete v0：相关实现集中在 `evidence_verification.py`，包含 `tier_rumor()`、`detect_causal_claim()` 与 `split_fact_from_inference()`；测试文件分别覆盖流言分级和因果说法拆分。后续如逻辑继续膨胀，再考虑拆成 `rumor_tiering.py` / `causal_claim_guard.py`。

## RANK：综合评估、精排与 Story Mix

目标：按板块进行热度、可信度、相关性、多样性和内容价值综合排序。

Issues:

- `RANK-001 Per-Section Ranking`：每个板块最多 10 条最终 story，不是全局 10 条。
- `RANK-002 CoreGameStoryPolicy`：游戏本身的新内容、新作、新发售日、新系统细节优先于泛讨论。
- `RANK-003 Source Dominance Audit`：防止单源带评论权重压过其他权威来源。
- `RANK-004 EditorialJudgment Shadow`：仅对边界样本调用 LLM，输出建议，不直接改 ranking。

Harness:

- `H-RANK-001`：五个板块分别选 story，单一来源不能占满所有位置。
- `H-RANK-002`：NS 板块内游戏新细节应高于泛泛"吃灰"讨论。

## GEN：内容生成与质量评估

目标：先验证内容本身，再考虑平台格式、长图和发布。

Issues:

- `GEN-001 Markdown Briefing`：输出带证据编号、可信度和素材状态的简报。
- `GEN-002 Platform Drafts`：生成微博、小红书、Bilibili 文案草稿，不新增事实。
- `GEN-003 ContentQualityGate`：按来源、候选、证据、核查、story、素材评分。
- `GEN-004 Human Review Pack`：让用户评分并决定高分风格。
- `GEN-005 Stable Review Artifact Contract`：当 run 已进入 `ready_for_content_review` 或 `needs_review`，稳定产出 `content_review.md`、`human_review_template.json` 与 manifest 索引，避免人工评分入口随条件分支消失。

Harness:

- `H-GEN-001`：流言必须带外部简化标签，不得写成已确认。
- `H-GEN-002`：内容质量报告能指出单源主导、热度弱、证据不足。
- `H-GEN-003`：真实 run 即使未进入 Phase 5，也必须生成人工 review 包；缺失时写 warning notification。

当前状态：`GEN-001/002/003` MVP complete。`GEN-004` MVP complete：`content_review.py` 可生成机器评分、story review lines、人工评分表和风格方向表。`GEN-005` complete v0：`v020_ultracode_verify` 修改 `should_continue_after_quality_gate`，write_content_review_pack 不再被 `run_story_cluster_review_agent` flag 跳过；只要 stories 非空就生成 review pack。

## LAY：版面设计与成图

目标：后置实现。读取已验证内容和素材，像 Word 导出 PDF 一样排版生成图。

### 目标结果

已验证内容能被转为可渲染版面，缺素材时留空标注，不用 LLM 补图。

### 最低验收标准

layout_manifest 只引用真实素材或 manual_fill_required；render_queue 不凭空生成资产；平台尺寸和内容块分开。

Issues:

- `LAY-001 Layout Manifest`：每个内容块绑定真实素材或 manual_fill_required。
- `LAY-002 HTML/CSS Renderer`：用 Playwright 渲染长图/轮播图。
- `LAY-003 Platform Constraints`：微博、小红书、Bilibili 尺寸、字数和截断策略分开。

Harness:

- `H-LAY-001`：缺图时留空并标注，不调用 LLM 生图补事实。

## OPS：运营、发布与服务化

目标：先半自动审核，再接平台发布；网页端读取通知和 artifact。

### 目标结果

发布前必须经过状态、通知、平台限制和人工确认门。

### 最低验收标准

blocking notification 时不发布；平台文案默认 draft；story 默认 unpublished；发布动作可追踪。

Issues:

- `OPS-001 Publish Checklist`：人工确认后再发布。
- `OPS-002 User Notification UI`：读取 `user_notifications.json` 显示阻塞、警告和待确认。
- `OPS-003 Platform Publisher Adapter`：后续按平台能力接自动发布。

Harness:

- `H-OPS-001`：blocking notification 存在时，发布流程必须停止。

## SVC：FastAPI / Nuxt3 内部工作台 ✅ (2026-06-17 implemented, 47/47 tests)

目标：先把现有确定性工程、SQLite 查询、LLM shadow、通知和人工评分入口产品化，形成内部可用的观察/评审界面；不在该阶段做自动发布、平台登录或让 LLM 直接改事实。

### 目标结果

内部工作台能把一次 run 从“目录里的文件”变成可浏览、可评分、可比较、可通知的产品界面。

### 最低验收标准

API 默认只读；run 列表、stage artifact、notifications、quality flags、shadow report、content review 可访问；人工评分只写 review 记录，不改事实产物。

Issues:

- `SVC-001 FastAPI Run/Artifact API` ✅：提供 `/runs`、`/runs/{run_id}`、`/runs/{run_id}/stories`、`/runs/{run_id}/candidates`、`/runs/{run_id}/notifications`、`/runs/{run_id}/artifacts`、`/runs/{run_id}/quality-flags` 只读接口，走 `persistence/agent_query.py`。`LangGraph/service/routers/runs.py`。
- `SVC-002 Nuxt3 Internal Workbench` ✅：提供 run 列表、run 详情、story 浏览器、阶段产物浏览，含参数设置面板。`LangGraph/workbench/`。
- `SVC-003 Human Review Capture` ✅：POST/GET `/runs/{run_id}/human-reviews`；写入 `human_reviews.json` + SQLite `human_reviews` 表，不修改 `stories.json`、`claims.json` 或 `platform_posts.json`。`LangGraph/service/routers/reviews.py`。
- `SVC-004 Read-only Safety Guard` ✅：middleware 阻挡路径穿越、任意 SQL、发布动作、非 GET/POST 方法；所有写操作必须是 review 端点。`LangGraph/service/guards/readonly.py`。
- `SVC-005 Project Skill Bridge`：重复三次以上的人工评审、artifact 审计、prompt 合同审查、source parser 调试流程，再沉淀成项目 skill；skill 只提供方法和 checklist，不承载事实数据。

Harness:

- `H-SVC-001`：给定 SQLite mirror 和 run manifest，run list API 返回 run_id、started_at、gate、score、open_notification_count。
- `H-SVC-002`：给定 staged artifact manifest，artifact browser 只能返回 manifest 登记产物，不能读取任意路径。
- `H-SVC-003`：提交人工评分后，只新增 human review record，不改最终 story、claim verification 或 platform draft。
- `H-SVC-004`：访问 `../.env`、任意 SQL 或 publish action 必须被拒绝，并生成可展示的安全/权限通知。

当前状态：planned MVP。进入实现前优先补 FastAPI/Nuxt3 目录骨架、OpenAPI schema、API fixture 和只读查询适配；先服务 `0.2.0` 的确定性主产物 vs LLM shadow 对比，不做平台发布。

## MEM：SQL、历史记忆与长期 RAG

目标：把 JSON artifact 镜像为 SQLite，支撑旧闻、重复、事件更新、历史背景和后续 RAG。

Issues:

- `MEM-001 SQLiteMirror v0`：离线 ingest 当前 output_dir，不替代 JSON。
- `MEM-002 SQL Event Store`：建立 news_items、games、events、event_news_links、decision_traces。
- `MEM-003 Historical Import`：导入 30-60 天或约 2000 条资讯作为评估集。
- `MEM-004 HistoricalContextMiner`：生成"自某年以后首次"等背景候选。
- `MEM-005 Publish Lifecycle`：为最终 story 和平台文案保留 `publish_status`、`published_at`、`platform_publish_id` 等字段，先默认 `unpublished/draft`。
- `MEM-006 AgentDBQuery`：为 Codex/Agent/FastAPI 提供只读白名单查询入口，避免未来 JSON artifact 不默认生成时只能扫目录或手写 SQL。

Harness:

- `H-MEM-001`：ingest 一个小型 output_dir，数据库行数与 artifact 一致。
- `H-MEM-002`：同游戏旧闻、同游戏新事件、同事件后续更新可查询区分。
- `H-MEM-003`：通过 `agent_query.py` 查询 runs、summary、stories、candidates、notifications、artifacts 与 quality-flags。

当前状态：`MEM-001` 已完成 MVP：`persistence/sqlite_mirror.py` 可离线 ingest `run_manifest`、raw sources、main/supplemental/rejected candidates、documents、evidence chunks、claims、claim verifications、story candidates、final stories、platform posts 和 user notifications。当前采用"核心字段 + raw_json"策略，避免过早把所有 artifact 拆成重 schema。`candidate_memory.json` 仍保留为轻量候选记忆，不等同于完整历史库。
`MEM-002`/`MEM-003`/`MEM-004` MVP complete v0：event store 建立 `news_items`、`games`、`events`、`event_news_links`、`decision_traces` 表结构；historical import 支持导入 30-60 天约 2000 条资讯作为评估集；`HistoricalContextMiner` 可生成"自某年以后首次"等背景候选。
`MEM-005` MVP complete：最终 story 和平台文案保留 `publish_status`、`published_at`、`platform_publish_id` 字段，默认 `unpublished/draft`。
`MEM-006` MVP complete：`persistence/agent_query.py` 提供只读白名单查询 API/CLI，支持 `runs`、`summary`、`stories`、`candidates`、`notifications`、`artifacts`、`quality-flags`；后续 Agent 和工作台应优先调用该入口，而不是直接扫描输出目录。

## AG：LLM、Agent 与 Skill 合同

目标：Agent 不接管主流程，只在边界明确时调用白名单工具，输出可审计建议。

Issues:

- `AG-001 AgentObservation/AgentDecision`：统一 Agent 输入输出。
- `AG-002 No Suitable Tool Handling`：Agent/LLM 判断没有合适方法时，输出 `needs_user_action` notification。
- `AG-003 SourceRecoveryAgent`：读取 trace/source health，建议重试、换入口、启用浏览器探针或人工复核。
- `AG-004 StoryClusterReviewAgent`：处理 `dedup_semantic_review_requests.json` 和 RAG evidence pack。
- `AG-005 Project Skills`：重复三次以上的工程流程再抽成项目 skill。

Harness:

- `H-AG-001`：给定 blocked source，Agent 只能从白名单动作中选，不新增事实。
- `H-AG-002`：所有工具都不适用时，输出通知而不是沉默失败或编造结果。

当前状态：`AG-001`/`AG-002` MVP complete：`agent_contracts.py` 定义了所有合同类型（`AgentObservation`、`AgentDecision`、`ToolResult`），统一 Agent 输入输出，包含 `no_suitable_tool` 时输出 `needs_user_action` notification 的 handling。
`AG-003`/`AG-004` MVP scaffold v0：`SourceRecoveryAgent` 已有确定性白名单动作选择器，并新增 `SourceRecoveryPolicy` 以避免恢复阈值散落在分支里；当前主流程的 `--run-source-recovery-agent` 仍先写 `source_recovery_plan.json`，尚未把 `SourceRecoveryAgent` 的 `source_recovery_decisions.json` 接为默认图节点。`StoryClusterReviewAgent` 已可处理 `dedup_semantic_review_requests.json` 和 evidence pack，但仍应保持 shadow/人工复核定位，不直接改最终事实。

## PRM：Prompt 统一管理

目标：让 LLM/Agent prompt 像代码接口一样可索引、可版本化、可回放、可禁用。Prompt 不直接代表功能完成，只有 registry、请求包、结果包、失败包和 fallback 都存在时，才允许进入可选执行。

用户能力描述：

- 开发者可以通过 `LangGraph/prompts/prompt_registry.json` 查看每个 prompt 属于哪个 issue、读取哪些 artifact、输出什么 JSON、失败时用什么 fallback。
- 开发者可以通过 `LangGraph/prompts/README.md` 按统一规则新增 prompt，而不是在节点里硬编码文件名和输出格式。
- 用户未来可以在网页端看到某个 LLM 任务用了哪个 `prompt_id/prompt_version`，以及失败后为什么回退到确定性规则。

Issues:

- `PRM-001 PromptRegistry v0`：统一管理所有 LLM prompt 文件、输入 artifact、输出 schema、fallback 和 harness 映射。
- `PRM-002 PromptFailureContract v0`：Prompt 解析失败、schema 不匹配、超时或拒答时写 failure artifact，回退到 registry 声明的 fallback。
- `PRM-003 Prompt Versioning`：prompt 文件改动时更新 registry version；后续 run trace 和 decision trace 记录 prompt version。
- `PRM-004 Prompt Encoding/Locale Audit`：检查 prompt 文件是否 UTF-8 可读，中文示例是否乱码，避免模型读取到损坏样例。
- `PRM-005 Prompt Eval Set`：把人工评分和 edge case 转为 prompt eval fixtures，后续接 LangSmith 或本地 eval。
- `PRM-006 Strict Structured Output Gate`：LLM 输出必须通过 JSON/schema/field consistency 校验；invalid JSON、字段矛盾、回显 input 或缺少 required fields 时写 failure artifact 并使用 fallback。

Harness:

- `H-PRM-001`：所有已注册 prompt 都有对应文件和合法 schema，registry entry 包含全部必需字段。
- `H-PRM-002`：模拟 parse/schema 失败时，写入正确的 failure.json 并使用 registry 声明的 fallback。

当前状态：`PRM-001/002` MVP complete v0：`LangGraph/prompts/README.md`、`prompt_registry.json`、`prompt_registry.py` 已建立统一入口；registry 现在包含稳定 `prompt_id`、version、status、task_type、input/output artifact、fallback、harness cases 和 default_enabled。`editorial_judgment.md` 已补齐，failure contract 可写入结构化 failure artifact。下一步是把 prompt version 与 shadow run/report 一起展示到服务化工作台。
`PRM-006` complete v0.1：`v020_ultracode_verify` 已落地 JSON repair、跨字段一致性检查和 echo detection。2026-06-17 审查发现 `llm_shadow.py` 的 required fields 曾与真实 prompt 合同不一致：query compression 实际输出 `queries/entities/confidence/risk_flags`，search relevance 实际输出 `results[]`，editorial judgment 实际输出 `judgment/game_relevance/publishability/reason` 等字段。已修正为按 task_type 分流校验，并补充 prompt-contract 回归测试，避免有效 LLM 输出被误降级为 fallback。

## LCA：LangChain 适配器

目标：把 Fetch、Search、SocialHeat、EvidenceRetriever 等核心能力包成标准化 LangChain tool/Runnable，复用 schema、retry、batch 和 structured output parser，方便未来服务化和 Agent 调用。

Issues:

- `LCA-001 LangChainAdapter v0`：把 Fetch/Search/SocialHeat/EvidenceRetriever 包成可测试 tool/Runnable，复用 schema、retry、batch 和 structured output parser。
- `LCA-002 ToolRegistry`：登记 tool_id、version、input_artifact、output_schema、retry_policy、batch_support 和 harness_cases。
- `LCA-003 StructuredOutputParser`：为每个 tool 提供 structured output parser，处理 JSON parse failure、schema mismatch 和 partial output。

Harness:

- `H-LCA-001`：每个 tool 可被 invoke、retry，并产出合法的 ToolResult。

当前状态：`LCA-001` MVP complete v0：`langchain_adapter.py` 已为 Fetch/Search/SocialHeat/EvidenceRetriever 提供标准化 tool wrapper，支持 schema、retry、batch 和 structured output parser；后续 `LCA-002`/`LCA-003` 将进一步把 tool 登记和 parser 契约独立出来。

## SHD：LLM 阴影任务

目标：只对小样本启用 LLM 阴影任务（query compression、search relevance、story cluster review、editorial judgment），输出 JSON 建议与人工评审包，不直接修改主流程的最终事实或排序。

Issues:

- `SHD-001 LLMShadowTasks v0`：只对小样本启用 query compression、search relevance、story cluster review、editorial judgment LLM shadow；输出 JSON 建议与人工评审包，不直接改最终事实或排序。
- `SHD-002 ShadowReviewPack`：把 shadow 建议和人类评审对比，生成 review pack 供后续调优和训练。
- `SHD-003 ShadowSamplePolicy`：定义小样本选择策略、频率限制和预算，防止阴影任务过度消耗 token。
- `SHD-004 Shadow Output Quality Gate`：shadow result 需要区分 success、usable_success、fallback 和 invalid_success；只有通过结构化质量门的结果才进入人工对比包。

Harness:

- `H-SHD-001`：shadow run 产出 results.json 和 failures.json，且不修改任何 main artifact。

当前状态：`SHD-001` MVP complete v0：`llm_shadow.py` 已为 query compression、search relevance、story cluster review 和 editorial judgment 提供 LLM shadow 执行器；shadow 输出写入独立 JSON 文件，不修改 story/claim/ranking/publish 等主 artifact。已补小样本输入压缩和 story/context pack URL 对齐，避免 editorial judgment 误读无关证据并降低 token 风险。0.2.0 的重点是用同一批输入对比确定性产物与 LLM shadow 产物，而不是让 LLM 直接接管主流程。
`SHD-004` complete v0.1：与 `PRM-006` 同期落地。shadow output 现在区分 success、ok_repaired、fallback_inconsistent 和 invalid_json；只有通过 `_validate_shadow_output` 全部三层检查（required fields、cross-field consistency、echo detection）的结果才标为 success。2026-06-17 审查后，`search_relevance` 字段矛盾（例如 `relevance=same_game` 但 `same_game=false`）不再被静默修成成功，而是进入 validation failure/fallback；`compressed_queries` 仅作为旧字段兼容归一化到 `queries`。

0.2.0 验收目标：

- 同一次 run 可以保留确定性主产物，并在显式开关下额外生成 LLM shadow 产物。
- shadow 任务必须记录 `prompt_id`、version、model、token_usage、input_artifact_refs、result/failure 和 fallback。
- shadow 输出不得改写 `stories.json`、`claim_verifications.json`、`platform_posts.json`、`publish_status`。
- 人工评审时可以看到 LLM 建议是否改善 query、搜索结果相关性、编辑路由和重复/连续事件判断。

## 未知异常通知策略

在 LangGraph 中，推荐把异常分为三类：

- transient：节点或工具可用 retry policy / fetcher retry 自动重试。
- recoverable：写入 state 和 artifact，经 conditional edge 进入 recovery branch 或 human review。
- blocking unknown：没有白名单工具可处理，写入 `user_notifications.json`，等待用户判断。

在 LangChain/Agent 中，工具不应靠自然语言"解释失败"结束，而应返回结构化 `ToolResult`：`ok=false`、`error_type`、`recoverable`、`suggested_actions`。Agent 如果发现所有工具都不适合，应输出 `AgentDecision(status="needs_user_action")`，再由 LangGraph 把它转成通知和中断/人工复核入口。

通知 artifact 字段：

- `notification_id`
- `severity`: `info`、`warning`、`needs_user_action`、`blocking`
- `stage`
- `issue_id`
- `title`
- `message`
- `details`
- `suggested_actions`
- `artifact_refs`
- `created_at`
- `status`: `open`、`acknowledged`、`resolved`

这样以后服务化时，网页端只需要读取 `run_manifest.json` 与 `user_notifications.json`，就能显示"哪里失败、为什么失败、下一步需要用户做什么"。
