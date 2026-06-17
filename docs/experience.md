# Experience Log

本文件保存运行复盘、调参观察和阶段性经验。`roadmap.md` 只保留路线决策、下一步计划和指向本文件的索引。

## EXP-2026-06-15-01 Story Mix 与主题精排

来源：`story_mix_policy_live`、`theme_reranker_live`。

关键观察：

- 旧版 story selection 曾把五个主题混在一起取全局 Top 10，导致补充板块和单源高分内容挤掉索尼、任天堂、微软、PC 板块。
- 修正为每板块最多 10 条后，数量问题明显缓解，最终 story 可超过 10 条。
- `ThemeSectionCarryover` 后，《艾尔登法环褪色者版》NS2 预购/容量这类来自 NS 板块的游戏本体新闻能回到任天堂板块。
- `ThemeReranker` MVP 能让 `core_game_update` 上浮，但 `editorial_intent` 早期过宽，`hardware_platform` + 泛 `update` 曾误判为 `core_game_update`。

启发：

- 主题拆分要先于全局精排；否则某个高量来源或补充板块会天然挤压平台板块。
- 板块内精排不能只看热度词，要区分游戏本体更新、平台商业、个人感悟、广告争议、拍卖/收藏、泛科技等编辑意图。
- 社交热度应是放大器，不应让无同事件证据的“热议/吐槽/网友称”压过游戏本体更新。

后续动作：

- 保留每板块 `per_section_limit=20` 和 `final_per_section_limit=10` 的策略。
- 继续校准 `editorial_intent`，但避免堆过多规则；模糊项进入 `EditorialJudgmentAgent` 或人工复核。

## EXP-2026-06-15-02 ArtifactStage 与 DedupLive 对比

来源：`outputs/langgraph/artifact_stage_live`、`outputs/langgraph/dedup_live`。

关键数据：

| 指标 | artifact_stage_live | dedup_live |
| --- | ---: | ---: |
| overall_score | 57 | 53 |
| candidates | 120 | 106 |
| supplemental_candidates | 174 | 143 |
| rejected_candidates | 351 | 307 |
| theme_candidate_pool | 92 | 92 |
| documents | 84 | 90 |
| claim_verifications | 92 | 92 |
| final stories | 47 | 48 |
| source health | healthy 3 / blocked 1 | healthy 1 / blocked 4 |
| dominant_source_share | 0.8299 | 0.988 |
| story source domains | Gamersky 42, PC Gamer 3, IGN 2 | Gamersky 48 |
| story_clusters | 92 | 92 |
| dedup_semantic_review_requests | N/A | 0 |

关键观察：

- `dedup_live` 的质量下降不是去重造成的。`story_clusters=92` 且每簇 1 条，说明本轮没有明显重复被合并。
- 分数下降主要来自英文/官方来源大面积 SSL timeout，最终 story 全部来自游民星空，单源支配更严重。
- `dedup_semantic_review_requests=[]` 暴露出另一个问题：确定性实体抽取太保守，尚不能稳定识别“同游戏不同细节”的连续事件候选。
- `artifact_manifest.json` 在 `dedup_live` 中正常生成，`copied_files=55`、`missing_files=0`，分阶段 artifact 组织可作为后续 Agent/LLM 读取入口。

启发：

- 先不要继续加重 dedup 规则；当前更重要的是来源健康、trace、可回放和源贡献审计。
- `SourceHealth` 和 `collector_errors` 应进入 SQL/run trace，否则同一次代码改动和网络波动会被误判为算法效果。
- `dedup_semantic_review_requests` 的触发需要更好的实体抽取来源，例如 title 中的书名号、英文游戏名、candidate tags、未来 RAG alias store 或 LLM classifier。

后续动作：

- 下一步优先做 `RunTrace + SQLite mirror`，记录每次运行的 source health、collector errors、artifact checksum 和阶段指标。
- `StoryClusterReviewAgent` 暂不进入主流程，只保留 `dedup_semantic_review_requests.json` 作为未来接口。
- 对来源健康做重试/缓存/离线回放设计，避免网络瞬时失败污染内容质量判断。

## EXP-2026-06-15-03 SQL、追踪与智能化入口

来源：本轮 dedup 复盘与 SQL/RAG/LLM/Agent 设计讨论。用户提供的 ChatGPT 分享链接无法读取，因此本条不引用该链接内容，只记录本项目当前判断。

核心判断：

- 项目已经进入需要“运行追踪”的阶段。否则无法区分：代码逻辑变化、网络失败、源站结构变化、候选质量波动、排序策略变化。
- SQLite 不应立刻替代 JSON artifact；更合适的是先做 mirror/index：JSON 继续作为人工可读和 git-friendly 输出，SQLite 用于查询、追踪、回放、RAG 检索和长期记忆。
- LangGraph 仍做主流程编排；LangChain 放到节点内部，承担 tool schema、retriever、structured output、LLM runnable、batch/caching。

推荐的追踪事件：

- `run_started` / `run_finished`
- `node_started` / `node_finished` / `node_failed`
- `source_fetch_started` / `source_fetch_finished`
- `artifact_written`
- `candidate_selected` / `candidate_rejected`
- `document_fetch_finished`
- `claim_verified`
- `story_selected`
- `llm_request_prepared` / `llm_result_applied`
- `human_review_recorded`

推荐的 SQLite 第一批表：

- `runs`
- `run_events`
- `artifacts`
- `sources`
- `source_fetches`
- `candidates`
- `documents`
- `evidence_chunks`
- `claims`
- `claim_verifications`
- `stories`
- `story_clusters`
- `social_heat_observations`
- `human_reviews`

后续动作：

1. 做 `RunManifest / TraceLog v0`：先写 JSONL，不改变主流程判断。
2. 做 `SQLiteMirror v0`：把一次 run 的 JSON artifact ingest 到 SQLite。
3. 做 `EvidenceRetriever v1`：基于 SQLite FTS/BM25 + metadata filter 返回 evidence pack。
4. 做 `StoryClusterReviewAgent`：只读取 `dedup_semantic_review_requests.json` 和 retrieved evidence，输出结构化建议，不直接改 facts。
5. 做 `ContentQualityAgent`：读取 scorecard、source dominance、theme sections 和人工评分，给下一轮调参建议。

## EXP-2026-06-15-04 SQL 事件库、联网失败与智能化第一步

来源：用户提供的 `某次大模型问答.md`、`dedup_live` 联网失败复盘、LangGraph/LangChain 官方文档。

核心判断：

- “先做好 SQL，导入约 2000 条资讯，再做确定性去重、事件聚合、RAG 与搜索智能化”是正确方向。它比先接一堆 LLM/Agent/LangSmith 更适合作为求职展示项目，因为它先证明数据建模、可追踪性和可回放能力。
- 需要微调的是：不要只是“顺着时间找新闻”，而是“以时间为主轴，以事件为单位组织”。资讯库的核心不是存 2000 条新闻，而是判断哪些是同一事件、旧闻复述、事件更新、同游戏不同事件或无关内容。
- SQL 应作为 source of truth；未来向量库只做 semantic search index；RAG/LLM 是推理和摘要层，不是事实源。
- LangGraph 不应放到最后，因为当前项目已经用它编排 workflow。应改为：继续用 LangGraph 编排状态与节点，先不上 LangSmith；等 LLM 节点真正影响决策后，再用 LangSmith 做 LLM/Agent observability、evaluation 和 monitoring。

联网失败与重试启发：

- 联网失败本身就是智能化第一步：系统应先确定性重试，再把失败状态暴露给 graph state、trace 和 SQL，最后才让 `SourceRecoveryAgent` 选择恢复策略。
- 不能粗暴“所有请求重试 5 次”。推荐默认 3 次；对高优先级源、疑似瞬时 timeout/429/5xx 可提高到 5 次；对 404、明确 URL 范围错误、解析规则错误不应反复请求。
- 重试必须带指数退避、jitter、`Retry-After` 支持、per-domain cooldown、总预算和 source-level 熔断，避免 retry storm。
- 当前 `HttpFetcher` 捕获错误并返回 `FetchResult`，节点不会抛异常，因此 LangGraph node retry 不会自动生效。短期应先在 fetcher/collector 层实现 attempt 记录；后续把工具包装成 LangChain Runnable 后，再用 `.with_retry()` 包住具体工具。

推荐的三层重试设计：

1. `HttpFetcher retry/backoff`：处理 transient network failure，输出 `attempts`、`final_error_type`、`retryable`、`cooldown_until`。
2. `LangGraph node retry_policy`：只用于会抛异常的外部 API/LLM/搜索节点。失败耗尽后进入 recovery branch，而不是悄悄吞掉。
3. `SourceRecoveryAgent`：读取 `source_health.json`、`collector_errors.json`、`run_events.jsonl`，在白名单动作里选择“重试同源、降低并发、换入口、启用详情页回填、启用浏览器探针、使用缓存、标记本轮需要人工复核”。

SQL schema 启发：

- `news_items`：原始资讯表，重点字段是 `publish_time`、`crawl_time`、`first_seen_time`、`last_seen_time`、`canonical_url`、`title_norm`、`content_hash`、`simhash`、`raw_json`。
- `games` / `news_game_links`：游戏实体与资讯的多对多关系，`match_method` 区分 `alias_exact`、`keyword_match`、`embedding_match`、`llm_judge`、`manual`。
- `events` / `event_news_links`：事件库核心，记录 `new_event`、`event_update`、`duplicate`、`stale_repost`、`same_game_different_event`、`irrelevant`、`uncertain` 等状态。
- `search_runs` / `decision_traces`：本地 trace 表，先对齐未来 LangSmith 需要的输入、输出、参数、阈值、模型、prompt version、分数和错误。

推荐近期顺序：

1. `SourceReliability v0`：fetch retry/backoff/cooldown + source failure classification。
2. `RunTrace v0`：`run_manifest.json`、`run_events.jsonl`，记录所有 fetch attempts 与 artifact 写入。
3. `SQLiteMirror v0`：先 ingest 现有 artifact，不替代 JSON。
4. `SQL Event Store v0`：建立 `news_items/games/news_game_links/events/event_news_links/search_runs/decision_traces`。
5. `HistoricalImport v0`：导入约 2000 条资讯或 30-60 天长窗口资讯，作为重复/旧闻/事件更新评估集。
6. `Search Intelligence Shadow Mode`：从 Query Compression / Query Expansion 开始，LLM 只给建议和候选 query，不影响主流程。

2026-06-15 落地进展：已新增全局 `docs/issues.md`，把后续 issue 按 roadmap 功能层和 harness case 管理；`HttpFetcher` 已实现最小 retry/attempt metadata，collector 已把 attempts 透传到 raw source 和 collector error artifact。未知异常不应靠日志散落处理，而应进入 `user_notifications.json`，供未来网页端、人工复核和 Agent recovery branch 统一读取。`RUN-001 RunTrace v0` 已接入 CLI，生成 `run_manifest.json`、`run_events.jsonl`、`user_notifications.json` 并进入 `artifacts_by_stage/run_trace/`。

2026-06-15 SQL 设计落地：确认 `candidate_memory.json` 不是完整历史库，而是候选 first_seen/last_seen/seen_count 记忆，用于旧闻复读和 follow-up update 的轻量判断。`MEM-001 SQLiteMirror v0` 已实现离线 ingest，把 raw/intermediate/final story/platform post/user notification 镜像到 SQLite；最终 story 默认 `publish_status=unpublished`，平台文案默认 `draft`，为后续 OPS 发布生命周期预留状态。

参考：

- LangGraph 文档把 transient network/rate-limit errors 归为适合系统自动 retry policy 的错误，并强调 state 只存 raw data、错误可进入 recovery flow：https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph
- LangGraph fault tolerance 文档说明 node timeout 失败后会清除该次写入，再交给 retry policy 判断是否重试：https://docs.langchain.com/oss/python/langgraph/fault-tolerance
- LangChain middleware 文档提供 tool/model retry middleware，适合后续把 Fetch/Search/LLM 工具包装成 agent tool 后做工具级重试：https://docs.langchain.com/oss/python/langchain/middleware/built-in
- LangSmith Observability 适合在 LLM/Agent 节点变多后追踪 traces、性能指标、反馈和监控；当前应先用本地 trace 对齐字段：https://docs.langchain.com/langsmith/observability

## EXP-2026-06-16-01 Issues 实现审计与智能化接入边界

来源：对另一个模型补全 `docs/issues.md` 所列功能后的代码、测试和 roadmap 进行审计。

关键判断：
- “有测试”和“已进入主流程”必须分开记录。很多新增模块已经有单测和 harness，但仍是 `flagged_node`、`shadow_mode` 或 `offline_tool`，不能写成 LLM/RAG/Agent 已经接管事实判断。
- 文档不能提前引用尚不存在的拆分模块。例如热度合同实际在 `social_heat.py`，流言分级与因果拆分实际在 `evidence_verification.py`，历史重复判断当前在 `event_timeline.py` 与 SQL event store 设计中。
- 未来会频繁调参或交给 Agent 选择的数值，不应只藏在分支里。本轮把 `SourceRecoveryAgent` 的恢复阈值抽成 `SourceRecoveryPolicy`，把搜索相关性阈值抽成 `SearchRelevancePolicy`。
- 搜索结果相关性分类的输入必须能表达“结果自己的时间、来源和元数据”。只把 `result_published_at` 塞进原候选对象，会让后续 LangChain tool/LLM structured output 很难复用。

后续动作：
- 先做 artifact schema registry 和 SQL/EventStore 端到端验证，再做 LangChain adapter。
- LLM 第一批只做 shadow：query compression、search result relevance、story cluster review、editorial judgment。输出 JSON 建议，不直接改最终 story。

## EXP-2026-06-16-02 Prompt registry 与功能文档化

来源：围绕 issues/harness、prompt 统一管理和后续文档清理的整理。

关键判断：
- `docs/issues.md` 不应只列工程任务，还要写清“用户可以通过什么做到什么”。这种能力描述可以直接转成 README、网页端帮助、harness 和验收用例。
- Prompt 是 LLM/Agent 的基础设施，不应散落在节点里。先用 `LangGraph/prompts/prompt_registry.json` 统一登记 prompt_id、版本、输入输出、fallback 和 harness，再考虑 LangChain structured output。
- Prompt 失败合同要早于 LLM 大规模接入。非 JSON、schema 不匹配、超时、拒答都应写入 `*_failures.json` 和 warning notification，不能把自然语言解释应用到 facts/ranking/publish drafts。
- 旧计划文档不一定要删除。只要它们仍能解释历史决策，就应在 docs 索引里标为 historical；真正的路线以 `roadmap.md`、`issues.md`、`experience.md` 和 `toolchain_decision_matrix.md` 为准。

后续动作：
- 实现 `PromptRegistry` loader 与最低字段校验。
- 把 prompt 文件中的乱码中文示例作为 `PRM-004 Prompt Encoding/Locale Audit` 处理，不在接 LLM 前忽略。
- 每个新增 LLM task 必须先补 registry entry 和 prompt_management harness，再接调用代码。

## EXP-2026-06-16-03 层级目标与 harness 目标化

来源：围绕“这些功能结束后，每个层要达成什么样的结果”进行的文档审视。

关键判断：

- 现有 `docs/issues.md` 已有功能层、issue、harness fixture 和“用户可以通过 X 来 Y”的能力描述，但还缺少每层完成后的结果定义。缺少这层目标时，测试容易退化成只验证命令能跑、JSON 能写，而无法判断结果是否符合产品目标。
- 层级目标应放在 `docs/issues.md`，因为 issue 和 harness 会跨阶段复用；roadmap 只记录路线影响和经验索引，避免把长验收表塞进路线图。
- 每层目标必须同时包含结果、最低验收标准和测试焦点。这样后续做 SQL、RAG、LLM、Agent 时，可以判断某个新模块是在补足目标，还是只是增加复杂度。
- `harness_only`、`shadow_mode`、`offline_tool`、`flagged_node`、`main_flow` 的升级不能只看测试数量，至少要有正向、失败、边界样本，并在真实或长窗口 replay 中证明不会污染事实链路。

后续动作：

1. 新增 issue 前先在 `docs/issues.md#层级目标与验收标准` 中找到对应功能层。
2. 新增 harness 时写清它验证的是“最低验收标准”还是“边界样本”。
3. 新增 LLM/Agent 能力时额外验证三件事：不新增事实、不新增 URL、不直接修改发布状态。
4. 下一步实现 `RUN-005 ArtifactSchemaRegistry v0` 时，应把 registry 的字段检查和用户通知映射回 RUN/MEM/PRM/AG 等层级目标。

## EXP-2026-06-16-04 Phase 4.57 审查、PDF 参考架构与 0.2.0 目标

来源：对另一个模型实现的 Phase 4.57 近期落地步骤进行代码/测试/文档审查，并读取 `智览AI项目组成参考.pdf`。

关键发现：

- Phase 4.57 的主要模块已经具备 MVP：`artifact_schema_registry.py`、`prompt_registry.py`、`langchain_adapter.py`、`llm_shadow.py`、SQLite mirror、EvidenceRetriever 和 HistoricalImport 均有测试覆盖。
- 原 `ArtifactSchemaRegistry` 测试通过但合同不贴合真实 artifact：它会把 `.jsonl`、Markdown、未登记可选 artifact 以及旧字段名误报为 invalid。修正后只校验关键 JSON artifact，跳过不适合该 registry 的产物。
- `run.py` 原本在 schema validation 之后追加 notification，但没有重新写回 `run_manifest.json` 和 `user_notifications.json`。这会导致未来服务端读不到 schema 校验通知。已修正为 schema validation 后重新写回 trace，并同步 staged artifact。
- `prompt_registry.json` 原本登记了 `editorial_judgment.md`，但文件不存在；测试还把这个缺口当成预期。已补齐 prompt 文件，并把 registry 提升为包含 `prompt_id/version/status/task_type/output_artifact/failure_artifact/harness_cases/default_enabled` 的 0.2.0 形态。
- `智览AI项目组成参考.pdf` 可作为服务化和工具链参考，但它是金融研报平台，不应照搬。对本项目最有价值的是 FastAPI/Nuxt3 工作台、Run/Artifact 可视化、Redis 缓存、LangGraph + LangChain 分层和 ECharts 数据看板。

0.2.0 目标判断：

- 0.2.0 不应追求自动发布、图片排版或完整生产部署。
- 0.2.0 应证明“确定性工程主流程”和“LLM 辅助 shadow 流程”可以并存、可比较、可回放。
- LLM 真实测试应从 query compression、search relevance、editorial judgment、story cluster review 的小样本开始。LLM 输出只写 shadow results/failures/report，不直接修改 facts/ranking/publish。
- FastAPI/Nuxt3 可以在 0.2.x 尽早启动，但第一版应是内部工作台：读取 run、artifact、schema report、notifications、content review 和 LLM shadow 对比，而不是自动运营平台。

后续动作：

1. 为 LLM shadow 增加一份固定 offline fixture，覆盖 positive、failure、boundary 三类样本。
2. 用一个真实 output_dir 跑 `--run-llm-shadow query_compression,search_relevance,editorial_judgment --llm-shadow-max-samples 5`，评估 token、格式失败率和人工可用性。
3. 规划 FastAPI/Nuxt3 工作台 MVP：run 列表、artifact 读取、content review 展示、shadow 对比、user notifications。
4. 继续保持 LLM shadow 与主事实链路隔离，直到人工评审证明某个 LLM 任务稳定增益。

## EXP-2026-06-16-05 v020 LLM shadow smoke、短标题修复与 AgentDBQuery

来源：`outputs/langgraph/v020_llm_shadow_smoke` 打印信息与 artifact 复盘。

关键观察：
- 采集侧数量已经不是主要瓶颈：本轮主候选 166、补充候选 212、拒绝 296，`theme_pool=100` 且五个板块各 20 条；正文抓取 84/92，覆盖率约 91%。
- 内容质量仍是 `needs_review`，分数 61。主要短板不是“跑不出 story”，而是讨论热度覆盖弱、单源主导、LLM/人工语义核查结果还没有进入评估闭环。
- LLM shadow 第一轮表现分化明显：`query_compression` 5/5 成功，适合继续做 0.2.0 对比；`editorial_judgment` 1/5 成功、4/5 fallback，且 5 个样本消耗 23k tokens，说明输入上下文太大、输出长度或 JSON 约束还需要收紧；`search_relevance` 没有样本，因为本轮 `search_expansion_candidates.json` 为空，不应误判为模型能力失败。
- 微软板块最后一条标题 `Xbox将` 的根因在候选阶段：游民星空 JSONP 列表中链接 `title` 属性被引号截断，但 link text、snippet 和详情页标题都包含完整标题。修复点应放在 parser/title quality guard，而不是 Markdown 渲染层。

已落地：
- `collectors/listing.py` 增加短标题回填：当 `title` 属性明显过短且 link text 是完整前缀时，用 link text 回填，并记录 `title_repair_count`。
- `claim_extraction.py` 增加二道保险：候选标题过短时，如果证据块的正文标题更完整，则用正文标题作为 claim/story 标题来源。
- `document_fetching.py` 增加空正文降级：页面解析不到正文时，优先用候选标题/snippet 填充最小 content，并标记 `content_fallback=candidate_text`；如果连候选文本也没有，再进入 document error。
- `persistence/agent_query.py` 提供 SQLite mirror 只读白名单查询 API/CLI：`runs`、`summary`、`stories`、`candidates`、`notifications`、`artifacts`、`quality-flags`。后续 Codex/Agent/FastAPI 应优先用该入口查库，而不是扫输出目录或临时生成 SQL。
- `llm_shadow.py` 增加输入压缩和 story/context pack URL 对齐：editorial judgment 不再按列表下标硬配无关 context pack，并且只传核心 story 字段和少量证据摘要。

后续动作：
1. 为 LLM shadow 增加固定 offline fixture，特别是 `search_relevance` 的正向、失败、边界样本。
2. 用真实 run 重新验证 `editorial_judgment`：重点看 token 是否下降、JSON 成功率是否提高、人工是否认为判断有增益。
3. 把 `agent_query.py quality-flags` 接入人工复盘或工作台，优先暴露短标题、空正文和 open notification。
4. 进入 FastAPI/Nuxt3 前，先要求真实 run 能通过 SQLite ingest + agent query + schema validation 的最低闭环。

## EXP-2026-06-16-06 v020_fix_verify 真实验证与 Agent 工程化下一步

来源：`outputs/langgraph/v020_fix_verify/打印日志.md`、`schema_validation_report.json`、`shadow_run_report.json`、`source_health.json`、`source_dominance_audit.json`、`selection_stage_diagnostics.json`、SQLite mirror 与 `agent_query quality-flags`。

关键观察：

- 上轮短标题和空正文问题已被真实验证覆盖：`schema_validation_report` 为 0 invalid，SQLite `quality-flags` 返回空列表，最终 `stories.json` 中没有 8 字以下短标题。微软板块不再出现 `Xbox将` 这类截断标题。
- 采集链路能形成可评估规模：原始候选 677，主候选 180，补充候选 230，拒绝 267；五个板块 theme pool 均达到 20，正文抓取 86/91，最终 story 43 条，其中索尼 10、任天堂 10、微软 7、PC 6、补充 10。
- 内容质量仍停在 `needs_review`：总分 61，主要问题是 `low_discussion_signal_coverage`、`single_source_story_dominance`、`no_llm_verification_results` 和 `rumor_without_llm_verification`。这说明系统已能产出候选和 story，但还不能声称“热点验证”和“语义核查”完成。
- `source_health` 暴露了非阻塞但需要可见的问题：Xbox Wire RSS 三次 SSL EOF 后失败，Nintendo Official 和 PlayStation Blog 因 48 小时内候选不足进入 `needs_fill`。本轮 `user_notifications.json` 为空，说明 warning 级来源问题还没有稳定传达给用户或后续 Agent。
- SearchExpansion + LLM 已从空跑进入可用样本：`requests=10`、`targets=20`、`ok=20`、`signals=10`、新增候选 9 条；`llm_query=3/3`、`llm_relevance=3/3`；shadow `search_relevance` 5/5 success。它证明 query compression 和结果相关性分类可以作为 0.2.0 的 LLM 对比点，但当前仍只应作为线索/讨论信号，不应直接变成事实证据。
- LLM 输出结构还不够硬：`editorial_judgment` token 从上轮约 23k 降到 7.7k，但仍 1/5 success、4/5 fallback，失败原因是 invalid JSON；`search_relevance` 虽然 5/5 success，但个别输出只回显 input 或缺少完整理由。SearchExpansion 的 LLM relevance 结果还出现 `relevance=same_game` 但 `same_game=false/confidence=0` 的不一致字段，说明结果接入前需要 schema gate、JSON 修复或 post-normalizer。
- `artifact_manifest.json` 记录 `missing_files=2`，对应 `content_review.md` 和 `human_review_template.json` 未生成。既然 Phase 4.5 的核心目标是让用户评估内容质量，人工评审包应更稳定地产出，而不是只在某些条件分支出现。

对 Agent 项目常见工程做法的映射：

- 主流程仍应是 workflow-first：LangGraph 负责节点、状态、条件边、重试和人工门；Agent 不直接改事实链路。
- Agent 常用能力应先落成“工具化 + 可审计”形态：白名单 tool、结构化 ToolResult、可追踪 run events、prompt registry、schema validation、fallback、人工 review pack、SQLite/RAG 查询入口。
- LangChain 适合逐步承担节点内部能力：tool/Runnable 封装、structured output parser、retry、batch、cache、retriever。它不应替代 LangGraph 的主编排，也不应成为事实来源。
- RAG 的近期价值不是聊天问答，而是为 editorial judgment、semantic relevance、duplicate/follow-up 判断提供 compact evidence pack。进入服务化前先把 SQLite/FTS 查询入口和 artifact contract 稳住。

下一步动作：

1. `GEN-004/005`：让 content review pack 稳定生成。即使 gate 是 `needs_review` 或 `ready_for_content_review`，也要写出 `content_review.md` 与 `human_review_template.json`，方便用户和后续工作台读取。
2. `PRM-006/SHD-004`：为 LLM shadow 增加严格结构化输出门。对 missing required fields、字段互相矛盾、回显 input、invalid JSON 的结果写 failure/fallback，不让它们被误当 success。
3. `RUN-006`：把 source_broken、needs_fill、missing expected review pack、LLM shadow 高 fallback rate 写成 warning notification；blocking 只留给会破坏事实链路的问题。
4. `MEM-006`：把 `agent_query.py` 作为未来 Agent/FastAPI 的默认数据库读取入口，先扩展查询视图，不让 Agent 扫目录或手写任意 SQL。
5. 0.2.0 的真实验收继续使用同一 output_dir 对比：确定性结果、SQLite mirror、schema report、quality flags、LLM shadow report、人工评分。

## EXP-2026-06-16-07 v020_ultracode_verify GEN-005/PRM-006/SHD-004/RUN-006 落地

来源：`EXP-2026-06-16-06` 的五项动作全部在本轮落地，同时完成 `docs/` 四文件更新和一次真实验证。

关键变更：

- **GEN-005**：`graph.py` 的 `should_continue_after_quality_gate` 不再跳过 `write_content_review_pack`。只要 stories 非空或 gate 为 pass/needs_review，就生成 `content_review.md` 和 `human_review_template.json`。`run_story_cluster_review_agent` flag 不再影响 review pack 生成。
- **PRM-006 / SHD-004**：为 LLM shadow 输出增加三层结构化门：(1) JSON repair 尝试修复尾逗号、无引号 key、markdown fence、不平衡括号后再解析；(2) 跨字段一致性检查（如 relevance=same_game 但 same_game=false 则标 fallback）；(3) echo 检测（LLM 只回显输入字段的判为 fallback）。`editorial_judgment.py` 新增 `_try_repair_json`、`_check_editorial_consistency`、`_detect_echo`、`_normalize_search_relevance_fields`；`llm_shadow.py` 新增 `_validate_shadow_output` 与 per-task-type 的 required fields 合同。
- **RUN-006**：新增 `run_notifications.py`，从 `source_health.json`、`shadow_run_report.json` 和 artifact 缺失检查生成 warning 级 notification。`run.py` 在 shadow pipeline 后调用 `build_all_run_warnings` 并 re-write `user_notifications.json`。Xbox Wire SSL EOF、Nintendo/PS Blog needs_fill、LLM shadow 高 fallback rate、content_review.md 缺失等不再静默。
- **工具链**：`toolchain_decision_matrix.md` 新增 "Agent Toolchain Direction After v020_fix_verify" 节，记录 LangGraph checkpoint/human-in-the-loop、LangChain structured output、本地 schema gate 优先于 LangSmith、agent_query 白名单等方向。

启发：

- 人工评审包 (content_review.md + human_review_template.json) 是 Phase 4.5 的核心交付物，不应被任何 feature flag 关掉。GEN-005 修的是架构优先级而非 bug。
- LLM 输出即使 parse 成 valid JSON，仍可能字段矛盾或回显 input。结构化门必须在 JSON parse 之后再加一层 validation/normalizer，否则 `success` 计数会虚高。
- Warning 级 notification 的价值不在单次 run 中显现，而在多轮 run 后 agent 或工作台能读取 `user_notifications.json` 判断 "这个 source 已经连续 N 轮 broken" 或 "LLM shadow 连续高 fallback，该修 prompt 了"。
- Ultracode 模式下四个问题串行落地 + 真实验证的总 token 远低于各模块独立分轮调试的累加，且文档同步避免遗忘。

下一步动作：

1. `GEN-006`：将 `content_review.md` 和 `human_review_template.json` 接入 `agent_query.py` 的 artifacts 视图，让工作台和 Agent 能读取评审包。
2. `PRM-007`：为 search_relevance 和 editorial_judgment 建立 offline fixture（正向/边界/失败样本各 ≥3），确保 schema gate 在无网络时也可测试。
3. `RUN-007`：为 `user_notifications.json` 增加 `acknowledged_at` / `resolved_at` 生命周期字段，支持工作台的状态流转。
4. 0.2.0 验收继续使用 `v020_ultracode_verify` output_dir。

## EXP-2026-06-17-01 v020_ultracode_review 审查与服务化工作台决策

来源：对另一个模型实现的 GEN-005、PRM-006、SHD-004、RUN-006 进行代码审查、单测回归和文档同步。

关键发现：

- 前 4 项总体方向正确：人工评审包稳定生成、LLM shadow 结构化门、warning notification、文档同步都符合 0.2.0 的路线。
- 主要 bug 在 `llm_shadow.py` 的 schema contract：校验器使用了旧的或想象中的 required fields，和真实 prompt 文件不一致，导致 query compression / editorial judgment 的有效输出可能被误判为 fallback。
- search relevance 的字段矛盾不应被静默修成成功。`relevance=same_game` 但 `same_game=false` 这类结果必须进入 validation failure/fallback，否则 shadow success 计数会虚高。
- RUN-006 通知里 `needs_fill` 曾读取不存在的 `candidate_count` 字段；真实 `source_health.json` 使用 `accepted_count`。如果不修，未来工作台会把 2 条候选显示成 0 条，误导人工判断。
- 服务化可以前置，但边界必须窄：FastAPI/Nuxt3 第一版是内部工作台，负责观察、评审、对比和记录人工标签，不负责自动发布、平台登录、LLM 事实改写或任意 SQL。

已落地：

- `llm_shadow.py` 按 task_type 对齐真实 prompt 合同：query compression 接受 `queries` 并兼容旧 `compressed_queries`；search relevance 接受 `results[]` 并校验 `same_game/same_event/current_window_valid/reason`；editorial judgment 接受 `judgment/game_relevance/publishability/reason`。
- `test_llm_shadow.py` 增加 prompt-contract 回归样例，覆盖成功、旧字段归一化、字段矛盾 fallback 和 editorial judgment 真实字段。
- `run_notifications.py` 的 needs_fill 候选数改为从 `accepted_count` 等真实字段读取，source_broken artifact ref 改为实际存在的 `raw_sources.jsonl`。
- 新增 `test_run_notifications.py`，确保 warning 文案和 artifact 引用可被工作台可靠使用。
- `docs/issues.md` 新增 `SVC` 功能层；`LangGraph/harness/service_workbench/` 新增 4 个工作台 harness；`toolchain_decision_matrix.md` 增加 service-first workbench 决策。

后续动作：

1. `SVC-001`：实现 FastAPI 只读 run/artifact/notification/quality/shadow API，优先调用 `persistence/agent_query.py`。
2. `SVC-002`：搭 Nuxt3 内部工作台骨架，先做 run list、run detail、artifact stage browser、content review、shadow comparison。
3. `SVC-003`：实现 human review capture，把人工评分、风格方向和采纳建议写入 `human_reviews`，不改主事实产物。
4. `SVC-004`：补 read-only guard，禁止任意 SQL、路径穿越和自动发布。

## EXP-2026-06-17-02 SVC-001~004 Workbench Implementation

- FastAPI: 9 read-only endpoints + human review POST/GET. SVC-004 readonly guard middleware.
- Nuxt3: run list, run detail, story browser, artifact stage browser, ParamSettings, ActionButtons.
- Tests: 47/47 passed, 4 harness JSONs marked implemented.
- Docs: root README with both Trae IDE and Linux server launch instructions (systemd + Nginx + crontab).
- API contract: docs/FastAPI/api-contract.md. Workbench guide: docs/Vue/workbench-guide.md.
