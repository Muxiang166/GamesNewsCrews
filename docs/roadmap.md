# 多智能体游戏资讯智能体路线图

目标：系统启动后自动寻找过去 48 小时内的新游戏相关资讯、玩家热梗、社区传播事件和平台争议，完成去伪存真、证据追踪、Markdown 简报、平台文案、版面设计和图片排版。后续再接内容运营角色进行半自动或自动发布。

## 当前 demo 复盘

初次运行使用 CrewAI 顺序流，目标是 `Nintendo Switch 2` 近 7 天资讯。实际结果偏离预期：

- 搜索阶段没有硬性时间过滤，结果集中在 2024-2025 的旧新闻。
- 最终简报的报告期是 `2024年11月 - 2025年4月`，与 2026-05-11 的当前时间不符。
- 资讯类型偏传统硬件发布复盘，没有覆盖高热度玩家讨论、梗图、离谱操作、社区截图等内容。
- 引用多为“综合报道”，缺少可回溯 URL。
- 44,517 tokens 对单次 demo 偏高。

评分：

- 运行过程：42/100
- 最终新闻：34/100

## Experience 索引

详细运行复盘与调参观察统一记录在 `docs/experience.md`。roadmap 仅保留会影响路线的结论。

- `EXP-2026-06-15-01`：Story Mix、ThemeSectionCarryover 与 ThemeReranker 的阶段经验。
- `EXP-2026-06-15-02`：`artifact_stage_live` 与 `dedup_live` 对比，说明 dedup 不是质量下降主因，来源健康和单源支配才是当前主要风险。
- `EXP-2026-06-15-03`：SQL、运行追踪、RAG/LLM/Agent 接入顺序经验。
- `EXP-2026-06-15-04`：SQL 事件库、联网失败重试、SourceRecoveryAgent 与搜索智能化 shadow mode。
- `EXP-2026-06-16-01`：Issues 实现审计，区分 main_flow、flagged_node、shadow_mode、offline_tool 和 harness_only。
- `EXP-2026-06-16-02`：Prompt registry、功能能力描述与 harness 文档化。
- `EXP-2026-06-16-03`：层级目标、验收标准与 harness 目标化，避免测试只验证“能跑完”。
- `EXP-2026-06-16-04`：Phase 4.57 落地审查、PDF 参考架构整理与 0.2.0 LLM shadow 测试目标。
- `EXP-2026-06-16-05`：v020 LLM shadow smoke 评估、短标题修复与 AgentDBQuery 查询入口。
- `EXP-2026-06-16-06`：`v020_fix_verify` 真实验证、LLM shadow 第二轮结果与 Agent 工程化下一步。
- `EXP-2026-06-16-07`：`v020_ultracode_verify` GEN-005/PRM-006/SHD-004/RUN-006 落地，结构化输出门、warning notification 和文档同步。
- `EXP-2026-06-17-01`：`v020_ultracode_review` 审查修复，LLM shadow prompt-contract 对齐、RUN-006 warning 候选数字段修复，以及 FastAPI/Nuxt3 内部工作台决策。

## 内容定义

系统优先寻找的不是“所有游戏新闻”，而是 48 小时窗口内值得传播的游戏信息：

- 官方硬新闻：游戏发售、延期、更新、召回、涨价、维护、财报、平台策略。
- 高热讨论：微博、Bilibili、贴吧、小黑盒、TapTap、Reddit 等平台大量讨论的事件。
- 玩家趣闻：离谱操作、聊天截图、游戏内事故、主播名场面、玩家自制梗图。
- 争议事件：价格、DEI、裁员、封号、退款、审核、外挂、服务器事故。
- 权威流言：被长期准确爆料者、权威媒体、权威自媒体、行业记者或可靠社区账号转发/引用的未证实消息，例如“舅舅党 CC 透露《GGGGG》极有可能于下月公布”。
- 历史上下文/纪录类调味剂：类似体育新闻里的“自 A/YY 年以后，B 是第一个做到 XXX 的游戏/厂商/玩家/平台”，用于增强可读性，但必须和事实结论分开标注。
- 梗图素材：高转发图片、视频封面、截图、评论区金句。

硬性过滤：

- `published_at` 或 `observed_at` 必须落在过去 48 小时内。
- 无法确定时间的内容进入待复核区，不直接进入主简报。
- 没有来源 URL 的内容不进入事实结论，只可进入线索池。
- 争议性结论必须至少有两个来源，或一个官方/一手来源。
- 流言类内容必须使用 `rumor`、`likely_rumor`、`unverified` 等状态，不得写成已确认事实。
- 历史纪录类补充必须能回链到历史证据库或外部权威来源；无法验证时只作为“可人工补充候选”。

## LangGraph 主流程

LangGraph 负责编排状态机，LangChain 负责搜索、抓取、检索、LLM 调用等工具层。

下图为 2026-06-16 实际实现的节点流（`graph.py`）。早期概念设计中的 SourcePlanner、SearchCollector、PageFetcher、DedupClusterer 等角色名已映射到下方具体节点；未实现的 Publisher 等延后节点未出现在当前图中。

```text
Trigger
 -> plan_sources
 -> search_candidates
 -> check_source_health (conditional)
 -> expand_search_candidates
 -> fetch_documents
 -> probe_discussions
 -> extract_assets
 -> deduplicate_stories
 -> build_event_timeline
 -> extract_claims
 -> verify_claims
 -> retrieve_evidence (conditional)
 -> score_heat
 -> mine_historical_context (conditional)
 -> plan_selection_backfill
 -> write_platform_posts
 -> validate_content_quality
 -> write_content_review_pack (conditional)
 -> write_material_bundle
 -> draft_markdown
 -> design_layout
 -> render_assets
 -> organize_artifacts
```

概念角色到实际节点的对应关系：

| 概念角色 | 实际节点 | 备注 |
| --- | --- | --- |
| SourcePlanner | `plan_sources` | 读取 source catalog、生成搜索计划 |
| SearchCollector | `search_candidates` | 多 collector 调度（RSS/listing/incremental/JSONP） |
| PageFetcher | `fetch_documents` | 正文抓取，含主题候选池分流 |
| AssetExtractor | `extract_assets` | 素材提取与缺图标记 |
| DedupClusterer | `deduplicate_stories` + `build_event_timeline` | 拆分到两层：候选去重与事件时间线 |
| ClaimExtractor | `extract_claims` | 候选到 claim 的确定性/LLM 拆解 |
| EvidenceRetriever | `retrieve_evidence`（conditional） | 证据检索，仅在 verify 不足时触发 |
| EvidenceVerifier | `verify_claims` | 规则 + 可选 LLM 语义核查 |
| ContextPackBuilder | 内嵌于 `fetch_documents`/`extract_claims` | context pack 在正文抓取和 claim 阶段生成 |
| HistoricalContextMiner | `mine_historical_context`（conditional） | 历史纪录/背景补充 |
| HeatScorer + StoryRanker | `score_heat` + `plan_selection_backfill` | 热度评分、主题精排与板块均衡 |
| MarkdownEditor | `draft_markdown` | 简报生成 |
| PlatformWriter | `write_platform_posts` | 三平台文案草稿 |
| ContentQualityGate | `validate_content_quality` | Phase 4.5 内容质量门 |
| —（新增） | `write_content_review_pack`（conditional） | 人工评审包生成 |
| —（新增） | `write_material_bundle` | Phase 4.5 物料包 |
| LayoutDesigner | `design_layout` | 版面计划（暂缓） |
| ImageRenderer | `render_assets` | 图片渲染（暂缓） |
| —（新增） | `organize_artifacts` | 分阶段 artifact 归档 |
| OpsReviewer / Publisher | 延后 | 未进入当前 graph |

## 角色与改动计划

### 1. SourcePlanner

职责：决定本轮查哪些来源和关键词。

改动：

- 增加固定来源表：IGN、GameSpot、PC Gamer、Eurogamer、VGC、Gematsu、游民星空、游侠网、3DM、机核、Bilibili、微博、贴吧、小黑盒、TapTap、Reddit、Steam、PlayStation Blog、Xbox Wire、Nintendo。
- 每个来源配置 `kind`、`region`、`priority`、`collector`、`supports_time_filter`。
- 生成站内搜索 query，例如 `site:ign.com game news after:2026-05-09`。

2026-06-16 实现状态：
- `config/sources.yaml` 已配置 IGN、GameSpot、PC Gamer、游民星空、Nintendo、PlayStation Blog、Xbox Wire 共 7 个 live 源，均含 `kind`/`region`/`priority`/`collector` 字段。
- 未配置 Eurogamer/VGC/Gematsu/游侠网/3DM/机核/Bilibili/微博/贴吧/小黑盒/TapTap/Reddit/Steam 源；部分社区平台预留为 DiscussionProbe/SocialHeatProvider 的后续实现目标。
- 站内搜索 query 生成已由 `search_expansion.py` 的 SearchExpansion v0 部分承接，但 query 生成方式以主题缺口短查询和事件词检测为主，非早期构想的 `site:` 搜索。

### 2. SearchCollector

职责：获取候选资讯和社区线索。

改动：

- 不再只依赖 DuckDuckGo。
- 优先接入支持结构化结果的搜索服务，如 Tavily、Brave Search、SerpAPI、Bing Search，后续按可用性选择。
- 对固定站点优先使用 RSS、站内页面、API 或稳定页面规则。
- 搜索结果统一成 `SearchCandidate` JSON。

2026-06-16 实现状态：
- 已不再依赖 DuckDuckGo。当前使用自研 multi-collector 架构：`media_rss`、`media_listing`、`media_incremental_listing`、`media_jsonp_paged_listing`（见 `collectors/registry.py`）。
- Tavily/Brave/SerpAPI/Bing Search 等第三方搜索服务尚未接入；SearchExpansion v0 使用公开 HTTP 搜索页观测作为替代。
- RSS 和列表页规则已稳定用于 IGN、GameSpot、PC Gamer、游民星空、Nintendo、PlayStation Blog、Xbox Wire。
- 所有 collector 输出已统一为 `SearchCandidate` schema。

### 3. PageFetcher

职责：抓取网页正文和元数据。

改动：

- 抽取标题、正文、发布时间、作者、canonical URL、图片、视频封面。
- 对 Bilibili、微博、小黑盒等动态内容预留浏览器抓取接口。
- 保存 `raw_sources.jsonl`，以后可复盘每条结论来自哪里。

2026-06-16 实现状态：
- `fetch_documents` 节点（`document_fetching.py` + `fetching.py`）已抽取标题、正文、发布时间、canonical URL 和图片 URL，输出 `documents.json`。
- `collectors/web.py` 提供 HTML 正文提取，支持 UTF-8/GB18030 编码。
- 浏览器抓取接口已预留（`collector=browser_sidecar` 占位），Bilibili/微博/小黑盒等平台当前以 `DiscussionProbe` 公开搜索入口为主。
- `raw_sources.jsonl` 已由 collectors 在 `search_candidates` 阶段持久化。

### 4. AssetExtractor

职责：提取可排版素材。

改动：

- 提取文章图、视频封面、OG image、玩家截图、梗图 URL。
- 标记版权/来源风险。
- 读取不到素材时生成 `manual_fill_required=true`。

### 5. DedupClusterer

2026-06-14 细化：去重应分成“候选级轻量去重”和“故事级事件聚合”，不能只做简单标题去重。新闻在固定时间窗内总量有限，候选级去重适合放在爬取信息后、板块归类后、正文取证前；它能减少重复抓正文和重复评分。故事级聚合则应放在 claim/story 阶段之后，用来区分“同一新闻重复转载”和“同一事件的后续补充”。

分层职责：

- `CandidateDedup`：在 `raw candidates -> main/supplemental -> theme_candidate_pool` 之间运行。按 canonical URL、去参数 URL、标题规范化、来源发布时间、游戏名/平台名、板块归类进行轻量聚类。
- `EvidenceMerge`：正文取证后，把同一 cluster 的多来源正文作为证据集合保留，不因为重复就丢弃来源。
- `StoryClusterer`：claim verification 后，把多条 claims/stories 聚合成 `story_cluster`，区分 `duplicate_report`、`same_event_followup`、`official_confirmation`、`new_detail_after_announcement`、`reaction_or_commentary`。
- `EventTimelineBuilder`：当一个事件在 48 小时内连续推进时，生成时间线而不是只保留第一条。例如“游戏公布发售日”之后，官方账号又公布主角设定、世界观设定或新预告，这不是重复新闻，而是同一事件下的新 detail。
- `ClusterReviewRequest`：当规则无法判断是重复还是后续补充时，写入 LLM/人工复核请求包，不直接删除。

短期实现边界：

- 先不接向量库，用 URL 规范化、标题 token/Jaccard、实体重合、发布时间接近和来源类型做规则版聚类。
- 去重输出必须保留 `cluster_id`、`cluster_role`、`representative_url`、`merged_source_urls`、`duplicate_reason`、`followup_reason`。
- 只有 `duplicate_report` 默认不重复进入最终 story；`same_event_followup` 和 `new_detail_after_announcement` 应作为同一 story 的补充段落或时间线条目。

***以下为旧版简要描述，已被上方 2026-06-14 细化方案覆盖，保留仅供历史参考。***

职责（旧）：去重和聚类。

改动（旧）：

- 先按 canonical URL 去重。
- 再按标题相似度、实体、时间、来源聚类。
- 同一事件保留多个来源作为证据，而不是丢弃。

***旧版描述结束。当前实现以 2026-06-14 细化方案为准。***

### 6. ClaimExtractor

职责：将资讯拆成可验证声明。

改动：

- 每个故事拆成 1-5 个 claim。
- claim 必须包含主体、动作、时间、对象、数值或状态。
- 不可验证的情绪表达单独放入 community_sentiment。

2026-05-15 最小实现状态：

- `claim_extraction.py` 已先实现候选级 claim scaffold：每个 `context_pack` 生成一个 `unchecked` claim。
- 输出 `claims.json`，保留 `source_urls`、`evidence_chunk_ids`、`missing_fields`、`claim_type`、`metadata`。
- 当前不调用 LLM、不做事实判断，只保证后续 `EvidenceVerifier` 有稳定输入 artifact。
- 下一阶段再用 LLM 将候选级 claim 拆成更细的事实断言，并将 context pack 升级为 claim 级 evidence pack。

### 7. EvidenceRetriever / RAG

职责：为每个 claim 检索证据包，是 RAG 的核心位置。

改动：

- RAG 不作为一个独立“角色”，而作为 `EvidenceVerifier` 背后的证据基础设施。
- 第一版先做轻量 evidence store：正文切块、metadata 过滤、关键词/BM25 检索；向量检索后续再接。
- 每个 evidence chunk 必须包含 `url`、`source_id`、`source_kind`、`title`、`published_at`、`observed_at`、`quote/snippet`、`credibility_hint`。
- 检索时优先按时间窗口、来源可信度、同一事件 cluster、claim 实体匹配过滤，再做文本相似度。
- 每个 claim 最多给后续 LLM 3-5 条证据，避免 token 膨胀。

建议新增模块：

- `evidence_store.py`：保存网页正文、切块和 metadata。
- `chunking.py`：正文切块，保留 URL、标题、时间、来源信息。
- `retrieval.py`：关键词/BM25/向量检索统一接口。
- `context_packs.py`：把故事、claim、证据、冲突证据、缺失项打包给 LLM。

2026-05-15 最小实现状态：

- `document_fetching.py`：只抓主候选 Top N；dry-run 下不联网，用候选标题和摘要合成可回放文档。
- `evidence_store.py`：将 `documents.json` 切成 `evidence_chunks.json`，保留 URL、source_id、标题、时间、quote、credibility_hint。
- `retrieval.py`：先用关键词检索，不接向量库，避免过早增加依赖。
- `context_packs.py`：为每个主候选生成 `context_packs.json`，后续 LLM 只读取紧凑证据包，不直接吃整篇网页。
- 当前还不做 claim 级检索；下一步等 `ClaimExtractor` 输出 claim 后，再把 context pack 从“候选级”升级为“claim 级”。

### 8. EvidenceVerifier

职责：基于 RAG 证据包去伪存真。

改动：

- 对每个 claim 输出 `verified`、`likely`、`rumor`、`conflict`、`reject`。
- 官方源权重最高，媒体源次之，社区源用于发现热度和玩家情绪。
- 对 DEI、亏损、涨价等因果性强的话题，必须区分“事实发生”和“原因推断”。
- 对权威流言输出单独状态：`credible_rumor`、`weak_rumor`、`unverified_rumor`，并保留“爆料者历史准确度/被谁转发/是否有二次信源”。

2026-05-15 最小实现状态：

- `evidence_verification.py` 已实现规则版 verifier scaffold。
- 输入 `claims.json` 和 `evidence_chunks.json`，输出 `claim_verifications.json`。
- 规则版只做 evidence chunk id / URL 绑定和关键词重叠评分。
- 非流言 claim 有足够重叠时标为 `likely`；流言 claim 有证据时仍标为 `rumor`；缺证据或弱匹配标为 `reject`。
- 当前版本不会输出 `verified` 或 `conflict`，这两个状态留给后续 LLM verifier 基于完整 context pack 判断。

2026-05-16 LLM verifier harness 状态：

- `llm_verifier.py` 已实现 LLM 请求包构建、LLM JSON 返回解析、LLM 结果合并。
- `verify_claims` 节点会额外输出 `llm_verification_requests.json`。
- 当前仍不直接调用 LLM；请求包先作为 harness artifact，方便人工检查 prompt/schema/context 是否合理。
- 后续接入模型时，只需要增加 provider 层读取 `llm_verification_requests.json`，返回 schema JSON，再调用合并函数。
- `prompts/evidence_verifier.md` 已固定 LLM verifier 输出格式。

2026-05-16 LLM provider 接入状态：

- `llm_provider.py` 已实现 OpenAI-compatible provider，优先读取 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`。
- CLI 新增 `--run-llm-verifier` 和 `--llm-verification-limit`；默认不调用 LLM，避免每次 dry-run 消耗 token。
- 启用后输出 `llm_verification_results.json`，再合并回 `claim_verifications.json`。

### 9. ContextPackBuilder

职责：做上下文工程，把结构化证据包交给 LLM，而不是传一整段上游自然语言。

改动：

- 每个故事生成一个 context pack，包含：故事标题、时间窗口、候选源、claims、evidence chunks、conflicting evidence、heat signals、missing fields。
- 官方、媒体、社区、流言来源分区展示，避免模型把社区情绪误判为事实。
- 没有原文、没有时间、没有素材的字段必须显式写入 `missing_fields`。
- 后续 `MarkdownEditor`、`PlatformWriter`、`LayoutDesigner` 只能读取 context pack 和结构化 state。

### 10. HistoricalContextMiner

职责：补充“连接过去与现在”的背景、纪录和类比。

改动：

- 从历史 evidence store、旧简报、官方数据库、Wikipedia/Steam/Metacritic/厂商财报等来源中查找关联背景。
- 生成类似“自 2017 年以后，Switch 系列首次出现 XXX”、“这是某厂商近 N 年内第一次 XXX”的候选句。
- 输出必须区分 `historical_fact`、`record_candidate`、`analogy`、`manual_review_required`。
- 纪录类内容默认作为简报调味剂，不参与主事实结论，除非证据非常明确。

### 11. HeatScorer

职责：判断是否值得写。

改动：

- 热度分 = 来源优先级 + 互动数 + 转发/评论速度 + 多平台传播 + 话题新鲜度。
- 没有互动数据时，用多源密度和社区出现频率做弱替代。
- 低热度但高重要性的官方新闻可保留，但不放在社媒头条。
- 权威流言如果被多个可信媒体/自媒体转发，可提高热度，但可信状态仍保持为流言。

综合排序支撑点：

- `freshness`：是否落在 48h 内，以及距离当前时间多近。
- `source_quality`：官方源、权威媒体、可信自媒体、社区源的不同权重。
- `evidence_strength`：claim 是否有证据、证据数量、是否同源复读、是否冲突。
- `verification_status`：`verified/likely` 高于流言；`conflict/manual_review_required` 只进待审或低位展示。
- `heat_signal`：评论、转发、播放、弹幕、跨平台传播密度。
- `story_type`：玩家趣闻、平台价格、重大硬件、争议、权威流言的权重不同。
- `content_fit`：是否适合微博/小红书/Bilibili 的标题、素材、图像化表达。

无法充分验证但广为流传的内容处理：

- 可以入选，但必须保留流言标签，不得写成事实。
- 正文标题或小标题必须出现“待验证”“未证实”“据称”“爆料称”等限定词。
- claim 状态优先使用 `credible_rumor`、`weak_rumor`、`unverified_rumor` 三档。
- 缺证据或冲突证据明显时，不进主内容，只进“待核查线索”或人工复核池。

2026-05-16 StoryRanker 最小实现状态：

- `story_ranking.py` 已将 `verified/likely/credible_rumor/weak_rumor/rumor` claim 聚合成 `stories.json`。
- story score 暂由热度、置信度、验证状态加权得到。
- `verified/likely` 默认 `ready`；流言类 story 默认 `needs_review` 并保留“有待验证”编辑标签。
- `reject/conflict/manual_review_required/unverified_rumor` 暂不进入 story 主列表。

### 12. MarkdownEditor

职责：生成可读简报。

改动：

- Markdown 必须引用证据编号。
- 每条新闻包含：标题、发生时间、热度原因、证据链、可信度、素材状态。
- 输出同时生成机器可读 JSON。
- 流言内容必须有明显标签，例如“未证实流言”“可信爆料”“待官宣”。
- 历史纪录类补充必须写成“背景补充/纪录候选”，避免误导为主新闻。

2026-05-16 最小实现状态：

- `markdown_editor.py` 已接管 `briefing.md` 生成。
- 简报读取 `claim_verifications`、证据摘录、LLM rationale、risk flags 和 artifact 路径，不再输出旧 skeleton 的“待接入模块”。
- dry-run 或合成证据会显式标注“流程验证输出，不可直接发布”。
- `verified/likely/credible_rumor/weak_rumor/rumor` 进入主简报候选；`unverified_rumor/conflict/reject/manual_review_required` 进入待复核线索。

### 12.5 PlatformWriter

职责：把 story 转成微博、小红书、Bilibili 的发布文案草稿，不新增事实。

改动：

- 输出 `platform_posts.json`。
- 只读取 `stories.json` 和结构化 state，不直接访问网络。
- 内部可以保留多档状态，但外部标签必须简单：
  - `credible_rumor` -> `[流言][可信爆料]`
  - `weak_rumor` -> `[流言][待验证]`
  - `unverified_rumor/rumor` -> `[流言][未验证]`
  - `verified/likely` -> `[已核实]` 或 `[证据支持]`
- 流言类文案必须带“有待验证”“尚未证实”“爆料称”等限定词。
- 缺图时标记 `manual_fill_required`，后续交给 `LayoutDesigner` 留空或做占位。

2026-05-16 最小实现状态：

- `platform_writer.py` 已生成三平台文案草稿。
- `write_platform_posts` 已接入 LangGraph 主链路，位置在 `score_heat` 之后、`draft_markdown` 之前。
- `briefing.md` 的本轮概览和产物索引会显示 `platform_posts.json`。

### 12.6 ContentQualityGate

职责：在进入排版、长图和平台格式适配之前，先评价内容本身是否值得继续加工。

改动：

- 输出 `content_quality_report.json`。
- 检查 source health、候选数量、正文抓取覆盖、热度信号覆盖、来源集中度、LLM 核查结果、流言是否未经语义核查、素材缺失比例。
- 对每个环节输出 0-100 分：
  - `source_collection`：真实来源是否健康。
  - `candidate_filtering`：候选是否充足、是否完成主/补充/拒绝分流、是否过度集中于单源。
  - `evidence_fetch`：正文和证据抓取覆盖是否足够。
  - `claim_verification`：规则核查和 LLM/人工语义核查覆盖是否足够。
  - `story_selection`：入选 story 是否足够、多样，是否被单一来源主导。
  - `platform_packaging`：平台文案是否生成，素材状态是否足够进入后续加工。
- 输出 `gate_status`：
  - `pass`：内容质量门暂未发现阻塞问题。
  - `needs_review`：内容可用于人工评估，但不应直接进入发布或成图。
  - `blocked`：真实采集失败或核心内容为空，不能评估内容质量。
- 输出 `overall_score` 和 `readiness`，用于判断是否只进入人工内容复核，还是可以进入 LayoutDesigner。
- 输出 `content_review.md` 和 `human_review_template.json`，让用户基于真实联网内容给人工分、选择风格方向、定义“什么内容应该高分”。
- 该节点不处理平台展示限制，不做字数裁切，不做长图分栏，只评价资讯内容本身。

2026-05-16 最小实现状态：

- `content_quality.py` 已新增内容质量报告。
- `validate_content_quality` 已接入 LangGraph 主链路，位置在 `write_platform_posts` 之后、`draft_markdown` 之前。
- `briefing.md` 会显示 content quality gate、issue 数量，并索引 `content_quality_report.json`。
- `briefing.md` 会显示每个环节的分数，方便正式联网验证时逐段定位问题。
- `content_review.md` 会把机器分、真实 story、证据摘录、文案预览和人工评分表放在一起，供用户决定风格方向。
- 根据 `outputs/langgraph/content_validation_live/briefing.md` 的本轮结果，当前内容应归类为 `needs_review`：真实来源 healthy，但仍存在热度信号不足、单一来源主导、LLM 语义核查未应用、素材缺失、正文抓取覆盖较低等问题。

### 13. LayoutDesigner

职责：把内容转成版面设计，不负责文生图。

改动：

- 输出 `layout_manifest.json`。
- 定义微博长图、小红书轮播、Bilibili 动态图等画布尺寸。
- 每个内容块绑定真实素材 URL 或 `manual_fill_required` 占位。
- 当前状态：暂缓。等 Phase 4.5 内容质量验证稳定后再继续，因为平台专有格式、板块分割和内容截断会反复调整，过早实现会掩盖内容质量问题。

### 14. ImageRenderer

职责：像 Word 导出 PDF 一样渲染图片。

改动：

- 优先使用 HTML/CSS + Playwright 截图。
- 后续可补 Pillow/ReportLab 做备用渲染。
- 不用 LLM 生成图，只用抓取到的真实图、截图、封面和模板排版。
- 当前状态：暂缓。等 LayoutDesigner 的内容块合同稳定后再实现。

### 15. OpsReviewer / Publisher

职责：发布前审核和运营。

改动：

- 第一阶段只生成发布包，不自动发布。
- 第二阶段做半自动发布清单。
- 第三阶段再考虑接微博、小红书、Bilibili 发布能力。

## Prompt / Context / RAG / Harness 工程

优先级：先做 harness，再做上下文工程，再做 RAG 工程，最后做 prompt 工程。

### 1. Harness 工程

职责：为整个 pipeline 提供可回放、可测试、可评估的运行夹具。

改动：

- 新增 `LangGraph/harness/`，保存样例候选、样例网页、样例 claim、样例流言、样例历史纪录。
- 支持不联网 replay：同一批输入可以重复跑出可比较结果。
- 记录每轮 run 的候选数、被拒数、入选数、缺图数、证据覆盖率、token 成本和耗时。
- 核心评估指标：recency precision、evidence coverage、source quality、heat relevance、rumor labeling accuracy、hallucination guard、cost。

### 2. 上下文工程

职责：决定每个 LLM 节点能看到什么、不能看到什么。

改动：

- 不把完整网页和上游 agent 长文直接塞给模型。
- 只传结构化 context pack，每个 claim 最多 3-5 条证据。
- 社区热度、官方事实、媒体报道、流言转述、历史背景必须分栏。
- 缺失内容显式标注，后续节点不得自行脑补。

### 3. RAG 工程

职责：为事实核查、流言分级和历史纪录补充提供证据检索。

改动：

- 第一版用关键词/BM25 + metadata filter。
- 第二版接向量检索，如 Chroma、FAISS、SQLite-vec 或 Qdrant。
- RAG 重点不是“生成答案”，而是为 `EvidenceVerifier` 和 `HistoricalContextMiner` 提供可引用证据。

2026-06-13 RAG 加入时机与完全体方向：

- 当前已经有 `evidence_store.py`、`retrieval.py`、`context_packs.py` 的轻量 RAG 骨架，但它还只是“证据打包/关键词检索”，不应急着升级成完整向量问答系统。
- RAG 的加入时机分三层：
  - `RAG-0 evidence scaffold`：当前阶段。用于把正文切块、保存 URL/source/time metadata、给 verifier 准备紧凑 context pack。
  - `RAG-1 claim-level retrieval`：在候选过滤、证据边界、主题池和社交热度接口基本稳定后加入。目标是为每个 claim 检索 3-5 条同事件、同时间窗、同主题的证据，支持 LLM verifier 和人工复核。
  - `RAG-1.5 event clustering support`：在去重和故事聚合进入规则版后加入。目标是检索同游戏、同发布会/直播、同官方账号、同时间窗的相邻证据，辅助判断候选之间是重复转载、后续补充、官方确认、玩家反应还是无关相似事件。
  - `RAG-2 persistent memory retrieval`：当多轮 live run 积累足够 story、claim、evidence、human review 后加入。目标是识别旧闻复读、follow-up update、历史纪录、爆料源准确率和“自某年以来首次”等背景。
  - `RAG-3 QA agent`：当证据库和记忆库稳定后，扩展成“资讯智能体 + RAG 问答”系统。用户可以问“过去 48 小时 Switch 2 涨价有哪些证据”“这个爆料可信度为什么高/低”“某游戏上一次出现类似争议是什么时候”，回答必须带引用和缺失说明。
- RAG 的进入条件：
  - 采集错误可分类，且主要来源能稳定产出候选。
  - `theme_candidate_pool.json` 能稳定达到可评估规模，至少 3 个核心板块有候选。
  - 每条进入 RAG 的候选都有稳定 `candidate_id/story_id/url/source_id/published_at_or_observed_at`。
  - `context_packs` 已区分 `candidate_url` 与 `retrieved_context`，避免跨 URL 参考上下文被误当事实证据。
  - `social_heat_observations.json` 或人工热度标签开始存在，避免 RAG 被迫承担“发现热点”的职责。
- 完全体 multi-agent 中的 RAG 角色：
  - `EvidenceGatheringAgent`：从 evidence store 检索 claim 证据。
  - `VerificationAgent`：基于 RAG evidence pack 判断 claim 状态。
  - `MemoryFreshnessAgent`：用历史 story/evidence 识别 late repost 与 follow-up update。
  - `HistoricalContextAgent`：查询历史 evidence store，生成纪录/背景候选。
  - `RumorProfileAgent`：检索爆料者历史准确率、被谁转发、是否被官方确认/否认。
  - `NewsQAAgent`：面向用户问答，只能引用 evidence/story/social heat/human review artifacts，不能凭空回答。
- 建议的长期存储分层：
  - `RunArtifactStore`：保留每轮 JSON/Markdown 产物，便于回放和审计。
  - `EvidenceStore`：SQLite + FTS/BM25 起步，保存正文 chunk、source、time、story cluster、claim ids。
  - `VectorIndex`：后续补 SQLite-vec/FAISS/Qdrant/Chroma，用于跨语言、同义表达和历史相似事件检索。
  - `StoryMemoryStore`：保存 story lifecycle、first_seen、last_seen、follow-up、最终状态。
  - `HumanReviewStore`：保存人工语义评分和风格偏好，作为 prompt/eval 校准集。
- RAG 仍然不负责：发现全网热点、绕过平台登录、修 parser、判断平台政策、生成没有引用的事实、替代社交热度采集。

### 4. Prompt 工程

职责：让 LLM 在明确 schema 和证据包内完成拆 claim、核查、写作和排版设计。

当前状态（2026-06-16）：`LangGraph/prompts/` 已创建，实际文件如下：

- `claim_extractor.md` — claim 拆解 prompt
- `evidence_verifier.md` — 证据核查 prompt（LLM verifier 输出格式）
- `markdown_editor.md` — 简报写作 prompt
- `platform_writer.md` — 平台文案 prompt
- `layout_designer.md` — 版面设计 prompt
- `historical_context_miner.md` — 历史背景挖掘 prompt
- `search_query_compressor.md` — 搜索 query 压缩 prompt（SearchExpansion 用）
- `search_result_relevance.md` — 搜索结果相关性分类 prompt（SearchExpansion 用）
- `prompt_registry.json` — prompt 统一注册表（id、版本、输入输出、fallback、harness）

改动：

- ~~新增 `LangGraph/prompts/`。~~（已完成）
- prompt 必须要求 JSON 输出，并和 `schemas.py` 对齐。
- prompt 不负责弥补采集和证据不足，缺证据时必须输出 `manual_review_required`。
- 后续新增 LLM task 必须先补 registry entry 和 prompt_management harness，再接调用代码。

### 5. LLM 接入边界

LLM 不进入确定性前置环节：

- 不负责 RSS/网页抓取、HTML 提纯、48h 时间窗、URL 范围过滤、候选类型分流、JSON 写入和图片渲染。
- 这些环节必须优先用规则、parser、测试和可复盘 artifact 解决。
- 但 LLM/Agent 可以作为“诊断与调度旁路”：读取采集诊断、页面样本、已观测 URL 和失败原因，提出应该调用哪个确定性 collector、如何调整入口或配置、是否需要浏览器探针/人工复核。LLM 不直接产出新闻事实、候选事实或证据结论。

LLM 进入高语义环节：

- `ClaimExtractor`：把文章拆成可验证 claim。
- `EvidenceVerifier`：基于 context pack 判断 `verified`、`likely`、`credible_rumor`、`conflict`、`reject`。
- `HistoricalContextMiner`：寻找“自某年以后首次 XXX”等历史背景，但必须带证据。
- `MarkdownEditor` / `PlatformWriter`：完成可读简报和平台文案。
- `LayoutDesigner`：把内容块、素材、缺图占位变成版面计划；最终渲染仍交给模板/HTML/CSS。

### 6. CrewAI 位置判断

主流程暂不接 CrewAI：

- LangGraph 已经负责状态机、分支、重试、artifact、人工介入和多节点协作。
- LangChain/自定义工具负责抓取、RAG、LLM 调用、结构化输出。
- 在主链路里再接 CrewAI 会形成双重编排，增加状态同步、调试、成本和可复盘难度。

CrewAI 可以作为可选 sidecar，用在更自由、更创作型、非阻塞的环节：

- `CreativePitchCrew`：基于已验证 story 产出 3-5 个标题角度、梗图角度、平台表达风格。
- `LayoutCritiqueCrew`：对 `LayoutDesigner` 的版面计划做创意审稿，提出更适合微博/小红书/B站的表达方式。
- `CommunityToneCrew`：读取补充池和社区素材，给运营口吻建议，但不能改事实状态。

CrewAI sidecar 的硬边界：

- 输入只能是已验证 context pack、story JSON、素材 manifest，不能直接联网发现事实。
- 输出只能进入 `creative_suggestions.json`，由 LangGraph 后续节点选择或人工审核。
- 不参与事实验证、不改证据、不决定是否发布。

后续新增和细化规则：

- 影响事实、候选入选、可信度、证据链或发布时间的能力，必须归入 LangGraph 主流程。
- 只影响表达风格、标题角度、版面审美、运营语气和平台化改写的能力，可以归入 CrewAI 创作 sidecar。
- roadmap 中所有 CrewAI 相关计划都放入本节或“Phase 6.5：CrewAI 创作侧车”，避免和主事实链路混写。

## Agent 工具契约与诊断调度框架

本节用于澄清“Agent 化”的方向：不是让 LLM 去爬取新闻、编造事实或替代证据，而是让 Agent 在每个阶段读取结构化状态，选择已有工具、诊断失败原因、提出可审计的下一步动作。事实仍然只来自确定性采集、网页正文、RSS/API、证据库和人工确认。

### 核心原则

- LangGraph 负责编排主状态机、分支、重试、人工介入和 artifact 落盘。
- LangChain 或自定义工具层负责把 collector、retriever、reranker、LLM provider 包成可调用工具。
- Agent 只输出结构化决策，不直接改事实库：`tool_call_request`、`config_patch_proposal`、`human_review_request`、`stage_score`。
- 自动执行只允许白名单工具和低风险参数；涉及新增来源、扩大抓取深度、登录态、平台发布、事实结论变更时必须进入人工复核。
- 每个 Agent 决策必须引用输入 artifact，例如 `source_health.json`、`collector_diagnostics.json`、`source_theme_counts.json`、`theme_candidate_pool.json`、`context_packs.json`、`claim_verifications.json`。

### Agent 模式选择：Workflow / ReAct / Reflection

本项目不采用单一 Agent 模式，而采用“三层组合”：

- `Workflow-first`：主链路必须是 LangGraph workflow。采集、正文抓取、证据切块、claim verification、story selection、content quality gate、平台文案和后续排版都应是可复盘节点。这样每次运行都有稳定 artifact，便于回放、评分、人工审查和测试。
- `Bounded ReAct`：ReAct 只用于局部工具选择和诊断调度，例如“这个平台应该走 public_search、browser_sidecar、manual_import 还是跳过”“这个来源候选少是分页不足、时间戳缺失还是入口太宽”。ReAct 不能直接写新闻事实，不能自由访问任意 URL，不能绕过登录/反爬，必须从白名单工具中选择，并输出 JSON 决策。
- `Reflection as review`：Reflection 只用于对已落盘 artifact 做复核和改进建议，例如对 `content_quality_report.json`、`social_heat_observations.json`、`source_dominance_audit.json`、`editorial_judgment_requests.json` 做二次评价，提出“下一轮该调权重、补平台、人工复核还是暂停进入 Phase 5”。Reflection 不应在 live crawling 中循环自我放大搜索范围。

对当前“收集和评估信息”流程的结论：

- 采集和评估主线用 workflow，因为我们需要稳定、可测、可审计。
- 站点/平台访问方式选择用 bounded ReAct，因为不同网站、社交平台、登录状态和解析器确实需要动态判断。
- 内容质量、热度可信度、非游戏混入和人工反馈校准用 reflection，因为这类问题适合在一次 run 完成后复盘，而不是边爬边自我循环。

### Build-vs-Buy 工具链评估门

项目已经进入真正的工程开头。之后每新增一个功能，不再默认“自研到底”，也不默认“先接一个流行 Agent 框架”，而是先通过 build-vs-buy 评估门：

- `must_use_existing_tool`：如果功能属于成熟基础设施，例如浏览器自动化、向量索引、结构化 LLM 输出、trace/eval，优先评估成熟库。
- `must_keep_custom_contract`：如果功能直接影响事实链路、候选边界、热度证据、人工复核或发布安全，必须先有项目自己的 JSON artifact contract，再把外部库包成 adapter。
- `deterministic_first`：能用确定性规则、metadata、时间窗、URL、source、平台状态先缩小范围的，不先交给 LLM。
- `rag_or_llm_only_after_artifacts`：语境/语义判断以后可以交给 RAG-backed agent 或 LLM classifier，但输入必须是 `candidate`、`social_heat_observation`、`evidence_chunk`、`story_memory` 等结构化 artifact，不允许模型凭空联网补事实。
- `optional_dependency_until_proven`：新库先作为可选 provider/sidecar，不进入主流程硬依赖；至少一轮 live run 和测试证明收益后，再考虑变成默认路径。

每个功能的评估记录至少包含：

- `function_area`：采集、社交热度、相关性分类、证据检索、记忆、精排、排版、发布等。
- `current_problem`：当前真实卡点。
- `candidate_tools`：可能使用的库或服务。
- `decision`：`custom_first`、`adapter_to_existing_library`、`defer`、`reject_for_now`。
- `reason`：为什么现在这样选。
- `integration_boundary`：输入/输出 artifact、是否可选、是否需要人工批准。
- `promotion_criteria`：什么时候从实验 adapter 升为默认实现。

详细矩阵见 `docs/toolchain_decision_matrix.md`，后续每新增一个 provider、RAG store、browser sidecar、LLM agent 或排版 renderer，都应先补一条决策记录。

当前工具链基线：

- `LangGraph`：继续作为主 workflow。官方文档区分 workflow 的预定路径与 agent 的动态工具使用，本项目需要前者作为主干，后者只做局部判断。
- `LangChain`：作为 LLM/tool/structured-output harness 候选，不替换 LangGraph 主流程。适合在 `RelevanceClassifierAgent`、`EditorialJudgmentAgent`、`VerificationAgent` 等节点封装模型调用。
- `Playwright`：作为 `browser_sidecar` 第一候选，用于 JS 搜索页、低频浏览器观察、后续排版截图；涉及登录或状态复用时必须人工批准。
- `LlamaIndex` / 向量库：作为 RAG-2/RAG-3 候选。短期仍用 SQLite/JSON + metadata/BM25；当出现跨语言、历史相似事件、长周期问答需求时再接。
- `Scrapy` / `Crawl4AI` / `Firecrawl`：作为采集/抽取 adapter 候选。只有当站点专用 parser 和普通 HTTP 明显成本过高时才引入，且输出仍必须落到现有 candidate/document/social heat artifact。
- `LangSmith` / eval 工具：当 LLM 判断开始影响排序或发布建议时再评估接入，用于 trace、成本、回归样例和人工标签评估。

2026-06-16 `v020_fix_verify` 后的 Agent 工程化判断：

- 当前最像成熟 Agent 项目应补的不是“让 Agent 全自动决定新闻”，而是把工具调用边界、结构化失败、可回放评估和人工门做扎实。
- 常见可复用基础设施应按风险分层接入：LangGraph checkpoint/human-in-the-loop 用于流程状态和人工门；LangChain tool/Runnable/structured output/retry 用于节点内部；SQLite/FTS 和后续向量库用于记忆与 RAG；Playwright 只用于 JS/浏览器侧取证或后续排版截图；LangSmith/本地 eval 在 LLM 建议开始影响排序前后再接。
- `SourceRecoveryAgent`、`EditorialJudgmentAgent`、`SemanticRelevanceAgent` 和 `ContentQualityAgent` 都应先以 shadow/review 形态读取 artifact，输出 `AgentDecision` 或 `*_results.json`，不直接写 `stories.json`、`claim_verifications.json` 或发布状态。
- `agent_query.py` 是 Codex/Agent/FastAPI 读取数据库的默认入口。未来即使 JSON 不默认生成，Agent 也应通过白名单 query 读取 runs、stories、candidates、artifacts、notifications、quality flags，再决定是否调用下一步工具。
- 任何 Agent 如果找不到合适工具，应输出 `needs_user_action` notification，而不是继续扩搜索、绕过登录、猜测网页结构或把自然语言解释混入事实链路。

成熟形态：

```text
LangGraph Workflow
 -> deterministic collectors/parsers/retrievers
 -> bounded ReAct tool routers for uncertain access/diagnosis
 -> reflection/review nodes for artifact critique and next-run decisions
 -> human approval gates for login, source expansion, publication, and fact-state changes
```

### 通用数据契约

- `AgentObservation`：某一阶段的输入快照，包含 `stage`、`run_id`、`artifact_paths`、`metrics`、`sample_records`、`errors`、`budget`。
- `AgentDecision`：Agent 的结构化判断，包含 `action_type`、`target_tool`、`params`、`reason`、`expected_effect`、`risk_level`、`requires_human_approval`。
- `ToolResult`：工具执行结果，包含 `status`、`artifacts`、`metrics_delta`、`warnings`、`errors`。
- `StageScore`：阶段评分，包含 `score`、`gate`、`blocking_issues`、`recommended_actions`。
- `ConfigPatchProposal`：配置修改建议，只能描述差异和理由，不直接静默修改 `sources.yaml` 等关键配置。

### 采集层 Agent

目标：当某个网站结构不同、抓取失败、48h 数量明显偏少、缺时间戳或主题覆盖异常时，Agent 能判断该调用什么确定性工具来解决。

建议组件：

- `SourceProfiler`：读取 source 配置、页面样本和历史表现，判断它更像 RSS、静态列表、分页列表、JS 增量加载、JSONP/API、详情页回填或需要浏览器探针。
- `CrawlHealthEvaluator`：基于 `source_health.json`、`collector_diagnostics.json`、`source_theme_counts.json` 判断候选数、missing_time、rejected ratio、blocked/error、主题覆盖和来源贡献是否异常。
- `CollectorRouter`：在 `media_rss`、`media_listing`、`media_incremental_listing`、`media_jsonp_paged_listing`、未来的 `browser_probe`、`manual_probe` 中选择合适 collector。
- `SourceRecoveryAgent`：只在采集结果不足或异常时运行，输出恢复方案，例如增加分类入口、调整分页深度、启用详情页时间回填、切换 JSONP/API collector、运行浏览器探针、请求人工确认。
- `SourceNavigator`：LLM 辅助的入口诊断器。它只读取已观测 URL、页面片段、导航链接和诊断指标，返回候选入口/配置建议，不直接生成新闻候选或事实。

采集层恢复顺序：

1. 读取现有 artifact，确认是数量少、时间戳缺失、主题错分、URL 范围过窄、页面被 JS 截断，还是网站阻断。
2. 优先调整确定性配置：`page_entries`、`feed_urls`、`pagination_url`、`max_pages_per_entry`、`stale_page_stop_count`、`allowed_url_patterns`、`detail_time_backfill_limit`。
3. 如果静态 HTML 不足，尝试已知动态接口、RSS、站点地图或详情页回填。
4. 如果页面依赖滚动/点击/JS，再调用浏览器探针，记录实际请求、链接和时间戳位置。
5. 如果仍无法判断，调用 LLM SourceNavigator 让它基于已观测材料提出入口和 collector 建议。
6. 如果涉及登录、反爬、版权或无法解释的结构变化，输出 `human_review_request`。

触发阈值建议：

- 某来源连续两轮 `raw_candidates == 0` 或 `error_count > 0`，触发来源诊断。
- 某来源 `missing_time_ratio > 0.3`，优先尝试详情页时间回填或动态接口。
- 五个主题板块中任一板块低于目标数量 50%，触发对应主题入口补搜。
- 某来源候选很多但入池少，触发 URL 范围、主题错分和噪声排除诊断。
- `theme_candidate_pool.json` 未达到目标但 `raw_candidates` 很多，优先检查过滤和分流；raw 本身少才扩入口。

### 检索、RAG 与精排层 Agent

目标：在已经收集到真实材料后，让 Agent 帮助“找证据、比相似事件、做精排”，而不是凭空补材料。

建议组件：

- `EvidenceGatheringAgent`：读取 story/claim，调用 evidence store、BM25/metadata filter、未来向量检索，返回可引用证据包。
- `RelevanceClassifierAgent`：用于 SearchExpansion 后处理，判断搜索结果是否同一事件、同一游戏、48h 内仍有效，是否旧闻、泛泛讨论、营销号搬运或标题党。
- `RerankAgent`：读取主题候选池、discussion signals、记忆库和证据强度，输出每个主题最多 20 条 story 候选，并为每个板块最多 10 条最终 story 写出排序理由。
- `MemoryFreshnessAgent`：比较新候选与历史记忆，区分 `new_story`、`late_repost`、`follow_up_update`。
- `HistoricalContextAgent`：只从历史证据库或权威来源补充“自某年后首次”等背景句，并输出 `confirmed_record/record_candidate/analogy`。
- `NewsQAAgent`：在完整证据库稳定后提供问答能力。它读取 story memory、evidence chunks、social heat observations、human review labels 和 final briefing，不直接联网找答案；回答必须带引用、时间窗和“不知道/证据不足”的说明。

LLM 在本层的合理用法：

- Query Compression：把候选标题、摘要、游戏名、平台名压缩成适合微博/Bilibili/贴吧搜索的短 query。
- Search Result Relevance Classification：对搜索结果做同事件/同游戏/时效性/旧闻/搬运/标题党判断。
- Semantic Rerank：在已收集证据内做语义排序，但必须输出引用的 evidence id。
- Conflict Detection：指出证据之间的矛盾和缺口，而不是自行裁决事实。
- RAG QA：把用户问题转成 metadata filter + hybrid retrieval，生成带引用回答；如果检索不到足够证据，必须输出 `insufficient_evidence`。

问答型能力的边界：

- 可回答：某事件证据链、某流言可信度、某平台热度依据、某游戏近 48h 变化、某公司近期争议脉络、某 story 为什么入选/未入选。
- 不可回答：没有抓取到的事实、实时平台后台数据、需要登录才能确认的内容、没有引用支撑的历史纪录。
- 回答数据源优先级：人工确认/官方源 > 候选自身正文 evidence > 权威媒体交叉报道 > 社交热度 observation > retrieved context 参考上下文。

### 验证、内容与后续发布层 Agent

- `VerificationAgent`：基于 context pack 和 evidence chunks 输出 claim 状态；缺证据必须返回 `manual_review_required`。
- `ContentQualityAgent`：读取各阶段评分和人工反馈，判断是否继续留在 Phase 4.5、是否可进入 LayoutDesigner。
- `MarkdownEditorAgent`：只根据 verified/likely/rumor-labeled story card 写简报，不新增事实。
- `LayoutPlanningAgent`：未来读取 story、platform post、asset manifest，规划内容块和缺图占位；不生成事实，不负责最终渲染。
- `OpsReviewAgent`：未来检查平台限制、敏感风险、发布清单和人工确认状态，再决定是否允许半自动发布。

### 分阶段落地顺序

1. 先补齐 Agent contracts 与 artifact schema：让每个阶段都能输出可诊断的 `Observation/Decision/ToolResult/StageScore`。
2. 采集层先做 `CrawlHealthEvaluator + SourceRecoveryAgent v0`：不自动改配置，只写 `source_recovery_plan.json`，用于解释“为什么候选少、下一步该试什么”。
3. SearchExpansion 接入 LLM query compression 与 relevance classification：保留现有关键词搜索 fallback，LLM 只负责短 query 和相关性标签。
4. RAG 层加强 evidence metadata、记忆库和旧闻/后续更新判断；稳定后再考虑向量库。
5. Story/theme 精排层加入可解释的 `RerankAgent`，把每个主题 20 条候选和每板块最多 10 条最终 story 的理由写清楚。
6. 内容、排版和发布 Agent 延后到 Phase 4.5 通过后再做，避免在内容质量未稳定时优化展示层。

### 当前结论

- 我们现在不是要“让 LLM 去爬新闻”，而是要把爬虫、检索、RAG、精排、写作、排版都设计成可被 Agent 调度的工具。
- Agent 的价值在于诊断、选择工具、提出下一步动作、解释评分和失败原因。
- 事实链路必须保持可复盘：候选来自哪个 URL，证据来自哪段正文，流言为什么被标注，排序为什么靠前，都要能回到 artifact。

## Token 成本控制

44,517 tokens 对单主题运行偏高。目标是把单轮 48 小时全局扫描控制在可解释范围内。

改动：

- 代码层先过滤时间、URL、重复项，再调用 LLM。
- 每个候选只传标题、摘要、时间、来源、正文片段，不传完整网页。
- 对每个故事 cluster 只保留 top 3-5 条证据。
- 使用 JSON schema 输出，减少反复解释格式的 token。
- 开启缓存：同一 URL 的抓取、摘要、claim 结果可复用。
- 低价值候选不用 LLM，直接丢弃或进入线索池。

## 阶段计划

### Phase 0：保留旧 demo

- 已归档到 `Demo/crewai_initial_demo`。
- 不再在 CrewAI 版本上继续扩复杂角色。
- CrewAI 后续不承担主流程职责，仅保留为原型归档、对照样本和 prompt 灵感来源。

### Phase 1：LangGraph 最小骨架

- 建立 `LangGraph/`。
- 完成 state schema、source catalog、空跑 graph。
- 先输出空 Markdown、layout manifest 和 render queue。
- 当前进展：已完成。dry-run 可生成 `briefing.md`、`layout_manifest.json`、`render_queue.json`。

### Phase 1.5：时间窗口与热度候选层

- 当前进展：已开始实现。
- 已新增候选过滤与热度排序模块：`games_news_agent.ranking`。
- 已用测试锁定两个核心行为：
  - 候选必须有 `published_at` 或 `observed_at`，且落在设定 lookback 窗口内。
  - 社区高互动梗图/玩家故事要优先于低互动普通新闻。
- dry-run 已加入示例线索，但这些是流程验证样本，不可发布。
- 下一步需要把 dry-run 示例替换为真实 collector 输出。

修改方案：

- `SearchCollector` 必须输出结构化候选，不允许只返回搜索摘要文本。
- 每条候选至少包含 `title`、`url`、`source_id`、`observed_at/published_at`、`heat_signals`、`tags`。
- 对微博、Bilibili、贴吧、小黑盒、TapTap、Reddit 等社区来源，优先记录评论、转发、点赞、播放、弹幕等热度信号。
- 对搜索引擎或媒体来源没有互动数据的候选，先使用来源优先级、发布时间和多源密度做弱热度判断。
- 没有时间戳的候选只进入 `rejected_candidates` 或人工复核池，不进入主简报。

### Phase 2：真实采集闭环

- 接入一个搜索服务和 3-5 个固定来源。
- 实现 48 小时时间过滤。
- 保存 `raw_sources.jsonl`。
- 首批建议接入顺序：
  - 固定媒体/RSS 或页面：IGN、游民星空、GameSpot、PC Gamer。
  - 社区热度入口：Bilibili 搜索/热门、微博搜索/热议、贴吧帖子列表、小黑盒资讯/社区。
  - 官方源：Nintendo、PlayStation Blog、Xbox Wire、Steam News。
- 如果平台反爬或登录限制阻碍采集，先把该平台 collector 标成 `manual_or_browser_required`，保留接口，不阻塞其它来源。

### Phase 3：验证与热度

- 实现 claim 拆解。
- 实现轻量 RAG：evidence store、chunking、metadata filter、关键词检索。
- 实现来源可信度评分。
- 实现热度评分。
- 实现流言分级：可信爆料、弱流言、未验证流言、冲突流言。
- 当前进展：Phase 3 的最小可测链路已成形。已完成规则版 claim extraction、规则版 evidence verification、LLM verifier 请求 harness、可配置 LLM provider、`StoryRanker`、`MarkdownEditor` 和 `PlatformWriter` scaffold；下一步正式转入 Phase 4.5 内容质量验证。

### Phase 4：内容生产

- 输出 Markdown 简报。
- 输出微博、小红书、Bilibili 文案。
- 输出素材缺失报告。
- 当前进展：Phase 4 初版已打通。`briefing.md` 和 `platform_posts.json` 已可由 dry-run/live run 生成；素材缺失先通过 `asset_status=manual_fill_required` 暴露。还不能算“内容生成完成”，必须先过 Phase 4.5。

### Phase 4.5：内容质量验证

- 暂缓平台展示、版面分割、内容截断和长图渲染。
- 先评价内容本身：48 小时准确性、候选混入、证据覆盖、来源可信度、热度支撑、流言标签、LLM/人工复核状态、素材缺失。
- 方向约束：不继续把关键词/正则扩展成自研分词或语义系统。词表只作为低成本前置过滤、可解释护栏和测试样例；语义判断、风格判断、流言分级和内容精炼应逐步交给 LLM、成熟分词/检索组件和人工评审闭环。
- 当前优先级：先联网收集真实物料，再基于 `content_review.md` 的人工评价校准评分权重和 LLM prompt；不要在缺少真实样本时继续堆规则。
- 输出 `content_quality_report.json`，并在 `briefing.md` 中显示 gate status、overall score、readiness、每个环节的 score 和主要问题。
- 输出 `content_review.md`，用于人工评价真实联网内容：是否值得写、是否热点、是否有梗、证据是否可信、标题方向是否接近目标风格。
- 输出 `assets.json` 和 `material_bundle.json`：先记录从原文读取到的图片/封面 URL、证据摘录、平台草稿、缺图标记和人工评分字段；不在此阶段下载图片或用 LLM 生成图片。读取不到素材时标为 `manual_fill_required`，后续排版阶段再决定留空、补图或替换素材。
- 2026-05-25 目标修正：Phase 4.5 的当前核心不是图片与排版，而是确认内容过滤和筛选质量。先实现 `EditorialFocusGate` 与 `DedupClusterer v1`，让网红/明星八卦不进入主线、PC 硬件/赛事营销默认进入补充池、同一事件合并为一个 story、高分/低分评分新闻单独识别、GTA 等真实游戏流言不被来源关键词误杀。
- 当前主线优先级：主机与游戏本身优先，包括 PS5/PlayStation、Nintendo Switch/Switch 2、Xbox Series X/S、跨平台重点游戏、评分解禁、发售/解锁/更新、玩家故事、争议、权威流言。PC 硬件、电竞活动、手游/网游先放低权重，除非它们成为玩家梗、重大争议或明确游戏事件。
- 正式联网验证流程：
  1. `collector_validation`：不跑 LLM，确认 4 个媒体源 source health、候选分流、正文抓取、混入率。
  2. `content_validation`：提高 `--document-fetch-limit`，对 Top N 候选抓正文和证据。
  3. `verification_validation`：对入选 stories 跑 LLM verifier 或人工复核，重点处理流言。
  4. `quality_review`：读取 `content_quality_report.json`、`content_review.md` 和 `material_bundle.json`，按机器环节分数、真实物料状态与人工评价共同决定是否继续；若人工评价显示主线混入、重复故事或低价值标题党，则继续停留在 Phase 4.5，不进入 Phase 5。
- Phase 5 的进入条件：
  - `overall_score >= 80`。
  - `readiness == ready_for_layout`。
  - 没有 `blocked` 环节。
  - `source_collection >= 80`，且没有 `source_collection_blocked`。
  - `claim_verification >= 70`，流言类 story 必须有 LLM 或人工复核。
  - `story_selection >= 70`，不得被单一来源完全主导。
  - 如果目标是“高热度讨论”，`heat_signal_coverage` 必须来自社区/搜索热度源支撑；仅媒体 freshness 不得标成高热。
- 当前进展：已开始。`ContentQualityGate` 已接入主链路；下一步是用真实联网结果反复校准质量阈值和问题分类。
- 2026-05-16 对 `outputs/langgraph/content_validation_live/` 的复盘：按 criteria 专用评分重算后 `overall_score=57`，`readiness=ready_for_content_review`。来源采集 100 分，但 `candidate_filtering/claim_verification/story_selection` 仍阻塞，因此继续留在 Phase 4.5。
- 2026-05-16 人工评分反馈：
  - 人工整体分：70；不允许进入 Phase 5。
  - 用户认为本轮“尚可，但范围太小，而且没有梗图等”。
  - 风格问题：更像新闻复制，不像“收集、评分、筛选后再交给 LLM/agent 风格化精炼”。
  - 应奖励：爆笑、争议、权威、玩家故事、硬件价格、流言准确率、新功能、多主机、PC 游戏。
  - 应惩罚：旧闻、单源、无热度、无证据。
- 已据此调整：
  - `candidate_types.py`：区分“爆料称/有望”与“已上线/报道/采访”，避免把已上线功能和正式报道误判成流言。
  - `evidence_verification.py`：中文证据 overlap 改用二字滑窗，并加入“部分证据支持”的低置信 likely 档。
  - `story_ranking.py`：新增 `editorial_fit_score`，奖励新功能、玩家故事、硬件价格、平台相关、权威/准确流言、争议；降低普通采访/玩法细节的优先级。
- 对已有真实联网 artifact 做离线重放后：`outputs/langgraph/post_review_replay/` 生成 5 条 story，首位变为“买 Steam 手柄送错国家！客服补偿：任选一款游戏送你”，第二位为“PS5 新功能上线/在线数据引热议”，普通采访玩法细节降到末位。该结果值得进行下一次真实联网验证。
- 2026-05-18 当前推进：Phase 4.5 新增真实物料包节点。`extract_assets` 会把正文中的 `image_urls` 写入 `assets.json`，`write_material_bundle` 会在人工评审包之后写出 `material_bundle.json`，用于下一次联网时一起评价“内容是否值得写”和“素材是否足够进入排版”。
- 2026-05-25 人工评分反馈：`outputs/langgraph/material_bundle_live/content_review.md` 显示联网链路已可用，但筛选仍像普通新闻站。需要剔除游民星空网红/明星内容，降低 PC 硬件营销活动，合并 FF6 AI 重制重复条目，保留高分评分新闻，并修复 IGN 中 GTA 流言被关键词门误杀的问题。结论：确认过滤和筛选前，继续暂缓图像与排版评估。

2026-05-26 热点判断修正：

- 本轮人工反馈指出：仍然没有抓住热点，不能只看某个网站的点击数或来源权重，而要看评论、转发、弹幕以及是否多个平台正在讨论。
- 已新增 `trend_signals.py`，把 `discussion_profile` 作为候选、context pack、claim metadata、story 和人工评审包中的一等字段。核心字段包括 `discussion_score`、`discussion_level`、`platforms`、`reasons`、`has_direct_engagement`、`has_multi_platform_discussion`。
- `HeatScorer` 降低了 `source_priority/freshness/media-source` 的基线权重；权威媒体现在主要证明“可信线索”，不能自动证明“热点”。真正的热点加分来自评论/转发/弹幕等直接互动、微博/Bilibili/Reddit/贴吧/小黑盒等多平台出现、以及明确的热议/疯传/大量玩家讨论语义。
- `ContentQualityGate` 新增 `discussion_signal_coverage`，低于阈值时输出 `low_discussion_signal_coverage`。后续进入 Phase 5 前，应先让联网结果在 `content_review.md` 中展示每条 story 的“讨论热度、讨论平台、讨论依据”，再由人工判断哪些方向应成为高分样本。
- 搜索模块下一步不应继续扩大普通媒体池，而应增加“讨论验证 probe”：对入围候选生成 2-4 个短查询，去固定社区/搜索入口寻找同事件在微博、Bilibili、Reddit、贴吧、小黑盒等平台是否有评论或转载证据。找不到讨论证据的条目可以保留为“权威新讯”，但不应标成“高热度热点”。

2026-06-01 主题板块修正：

- 固定文字板块改为五块：`sony` 索尼、`nintendo` 任天堂、`microsoft` 微软、`pc` PC、`supplemental` 补充板块。
- 新增 `story_sections.py`：先将所有 publishable story 分入五个主题板块，每个板块最多保留 20 个高分 story 候选，再在每个板块内最多选出 10 条最终 story。
- `stories.json` 表示五个板块分别入选后的最终 story 集合，总数不再强行限制为全局 10 条；`story_candidates.json` 保存进入主题池前的全量 story 候选；`theme_sections.json` 保存五个板块的候选数、入池数、入选数和板块内入选 story。
- `briefing.md` 与 `content_review.md` 按主题板块展示入选故事，便于人工判断到底是某一平台偏多，还是某一板块本轮确实更热。
- 中文/英文来源策略：同一 story cluster 同时有中文站和 IGN 等英文来源时，优先采用中文标题和中文来源 URL；没有中文版本时才使用英文版本，并保留 `source_preference` 字段标记 `english_ign_fallback` 或 `chinese_source_preferred_ign_context_available`。
- 已将主题选择前移到正文抓取阶段：`fetch_documents` 先写出 `theme_candidate_pool.json`，从 main candidates 与 supplemental candidates 中按五个主题板块各取最多 20 条。
- 2026-06-11 修正：主题候选池上限与正文抓取上限已拆分。`--theme-candidate-pool-limit` 控制 `theme_candidate_pool.json` 保留多少条平衡主题候选，默认 100；`--document-fetch-limit` 控制每个主题板块本轮最多实际抓取多少篇正文。`theme_candidate_pool.json` 会记录 `fetch_limit_scope=per_section`、`fetch_candidates`、`fetch_selected_count` 与 `dropped_before_fetch`，用于区分“候选池不足”和“本轮抓取预算较小”。
- 如果 `theme_candidate_pool.json` 仍不足 100，优先判断为源头候选量、48h 时间窗口、候选分流或 collector 深度不足，而不是正文抓取参数失效。下一轮应看 `source_health.json`、`candidates.json`、`supplemental_candidates.json` 与 `theme_candidate_pool.json` 的板块计数，决定是否增加分页抓取、社区讨论 probe 或更多权威中文源。

2026-06-06 检索侧优先级修正：

- 当前不应先进入“完整 RAG 阶段”。项目已经有轻量 evidence store、chunking、关键词检索和 context pack；候选资讯少的问题发生在 RAG 之前，RAG 只能验证和重排已抓到的材料，不能凭空发现 48 小时热点。
- 下一步优先做 `SearchExpansion`：扩充权威源入口、同源多 feed/listing 入口、分页或分类页抓取、source health 细分、候选池主题覆盖率统计。目标是让 `theme_candidate_pool.json` 在真实联网时能更接近 5 个板块各 20 条。
- 已为 `SearchCollector` 增加多入口设计：同一 source 可配置 `feed_urls` 或 `page_urls`，registry 会逐个抓取并合并候选与 raw source 记录。这样后续可以为 PlayStation Blog、Xbox Wire、Nintendo、IGN/GameSpot 分类入口等增加主题入口，而不需要把同一媒体拆成多个重复 source。
- 新增 `source_theme_counts.json`：在 `search_candidates` 阶段持久化每个来源在索尼、任天堂、微软、PC、补充板块中的候选数量，同时记录 raw candidate、main、supplemental、rejected 和 reject reason。运行时也会打印类似 `IGN: 索尼=5条，微软=2条` 的摘要，方便判断扩源是否真的补到了短板。
- 新增运行进度打印：CLI 会按 LangGraph 节点输出 `plan_sources/search_candidates/fetch_documents/verify_claims/score_heat/validate_content_quality/draft_markdown` 等阶段摘要。联网验证时用户可以看到当前跑到哪一步，以及候选池、正文抓取、评分结果的大致情况。
- 2026-06-06 `source_metrics_live` 复盘：`theme_candidate_pool.json` 只有 62/100，索尼 8、任天堂 10、微软 4，PC 和补充板块已满；`source_theme_counts.json` 显示微软主题尤其缺口明显。因此把已有的 `nintendo`、`playstation_blog`、`xbox_wire` 从 stub 改为 live RSS 源。它们的定位是御三方官方基础覆盖和权威证据，不是热点证明；高热度仍需 `DiscussionProbe` 或多平台转载/评论信号支撑。
- 2026-06-06 `official_sources_live` 复盘：官方源接入后候选池从 62 提升到 74/100，PC 和补充板块已满，微软因 Xbox Wire 明显改善；索尼、任天堂仍未稳定达到每板块 20。这个数量已足够开始做检索侧持久化，但还不足以宣布检索侧完成；后续应继续补权威中文源、主题分类页和讨论热度 probe。
- 新增 `CandidateMemoryStore v1`：先用 JSON 文件持久化已经通过基础过滤的 main/supplemental 候选，默认路径为 `outputs/langgraph/memory/candidate_memory.json`。第一版记录 URL/title key、first_seen_at、last_seen_at、seen_count、source_ids、published_at_values，用于后续将旧闻复读标成 `late_repost`，或把带当天变化的新报道标成 `follow_up_update`。
- 当前不急于上完整数据库。JSON 记忆库用于验证行为和人工复盘；等候选量、字段和相似新闻判断稳定后，再迁移到 SQLite（结构化记录 + FTS/BM25），并在需要语义近似时补 SQLite-vec/FAISS/Qdrant。
- 2026-06-06 `official_sources_live` 深度复盘：本轮 raw candidates 1505，基础过滤后 80 main + 121 supplemental，拒绝 1304；`theme_candidate_pool.json` 实际入池 74/100，五个板块为索尼 11、任天堂 10、微软 13、PC 20、补充 20。`--document-fetch-limit 100` 没有成为瓶颈，真正的主题缺口仍在源头覆盖和主题分类。
- “入池多但最终入选少”的早期原因不在检索限制：74 个 context/claim 经过规则核查后产生 62 个 story candidates，但旧版 `theme_sections.json` 曾按全局 `final_limit=10` 只取最终 Top 10，导致补充板块和单源高分内容挤压索尼/任天堂/微软。2026-06-15 已将 Story Mix Policy 修正为“每板块最多 10 条最终 story”，后续重点转为板块内精排、去重聚合、热点证据优先、低价值补充降权，而不是继续单纯加大 `--document-fetch-limit`。
- 网站检索方式的当前问题：游民星空 raw 很多但 `missing_time` 占比极高，需要更稳定的列表/详情页时间抽取；PC Gamer 产出多但大量进入 supplemental，需要更细的 PC 新闻/硬件/折扣分流；官方 RSS 能补权威证据但数量少、热度弱；IGN/GameSpot 需要继续用 URL/关键词规则排除影视、购物和泛娱乐。
- `collector_errors.json` 中的 homepage XML parse 错误来自旧的 registry fallback：配置了 `feed_url`/`page_url` 后仍额外抓 source 首页。该问题已在 collector registry 修复；下一次 live run 应重新生成 `source_health.json`，不能用旧 artifact 的 `source_collection=blocked` 作为当前代码状态。
- `source_health` 后续应区分“局部入口告警”和“来源整体不可用”：当某源候选数已达标时，非阻塞 collector warning 不应把整站判成 `source_broken`，但仍要保留 `error_count` 和 explanation 供排查。
- 检索方式诊断标准已沉淀到 `docs/retrieval_strategy.md`：以后判断是否能进入 RAG，不再只看候选总数，而要看错误是否可分类、时间戳是否可回填、主题池是否稳定、来源贡献是否可解释、以及是否至少有一条媒体事实 + 社区讨论的热点链路。
- 已开始实现 `CollectorDiagnostics v0` 和 `SourceNavigator v0`：`search_candidates` 会写出 `collector_diagnostics.json`、`source_navigation_requests.json`、`source_navigation_results.json`。默认只生成请求包，不调用 LLM；传入 `--run-llm-source-navigator` 后才会让 LLM 在已观测 URL 中推荐入口。游民星空先配置 `detail_time_backfill_limit: 12` 做低限额详情页时间回填实验。
- RAG 的下一步只做“检索质量护栏”，不先接向量库：为 context pack 增加 source/theme/time metadata filter、证据覆盖率报告、旧闻/后续更新对比入口。等候选数量和主题覆盖稳定后，再考虑 BM25 或向量检索。
- 讨论热度仍需要独立 `DiscussionProbe`：对主题候选生成短查询，到固定社区/搜索入口确认微博、Bilibili、Reddit、贴吧、小黑盒等是否有评论、转发、弹幕或多平台讨论。它属于检索侧增强，不属于 RAG。
- 联想式搜索暂缓到“真热点”可被稳定识别之后：例如夏日游戏节开幕会天然引出“新作首次公布/新内容公布/试玩反馈”等查询扩展，但这应建立在 `DiscussionProbe` 能证明某事件正在被讨论之后。否则联想搜索会放大普通发布会新闻和内容农场，重新把系统带回“新闻多但不热”的方向。

2026-06-07 `diagnostics_live` / `navigator_live` 复盘：

- 两轮结果高度一致：不启用 LLM 时 `main=68, supplemental=108, rejected=166`；启用 SourceNavigator 时 `main=68, supplemental=109, rejected=166`。这说明 SourceNavigator 当前只影响诊断建议，不影响主内容链路。
- 检索数量已达到进入下一层的最低要求，问题不再是“普通媒体候选太少”，而是讨论热度证据少、单源 story 多、补充板块仍会混入非游戏内容。
- `source_collection=89` 和 `evidence_fetch=91` 已经通过；`candidate_filtering=67`、`claim_verification=55`、`story_selection=56` 继续阻塞 Phase 5。下一步仍留在 Phase 4.5。
- 已修正 SourceNavigator 请求顺序：不再按配置顺序消耗 LLM limit，而是按诊断痛点排序。用本轮产物离线重算后，limit=3 会优先检查 `gamergen -> nintendo -> ign`。
- 已为 live `search_candidates` 增加节点内部进度输出：source start/done、详情页时间回填 start/done，解决“看起来卡住”的可观测性问题。
- 已对游民星空增加明显非游戏娱乐/带货排除词，先降低 papi 酱宠物用品等综合站噪声进入补充板块的概率。
- 下一步优先做 `DiscussionProbe v0` 和 story/theme 精排护栏：候选已够，不再优先盲目增加 RSS；只有 Nintendo 官方更及时入口、游民星空时间回填失败原因、IGN 更窄入口这三类检索问题需要继续小修。

2026-06-08 `DiscussionProbe v0` 实施：

- 新增 `discussion_probe.py`，负责生成低频/人工搜索入口，并从候选与正文 evidence quotes 中识别讨论平台、热议语言和多平台复现。
- 新增 LangGraph 节点 `probe_discussions`，位置在 `fetch_documents` 之后、`extract_assets` 之前。这样它能使用正文证据，又能在 `extract_claims` 前把讨论分数写入 context pack 和 claim metadata。
- 新增产物 `discussion_probe_requests.json` 和 `discussion_probe_report.json`。
- CLI 新增 `--discussion-probe-limit`，默认处理 20 个主题候选。
- v0 不直接爬社交平台、不调用 LLM、不改写事实，只提升 `discussion_profile`，且合并策略为只升不降。
- 下一步要用真实 live run 评估：如果 `discussion_signal_coverage` 明显提升但 story 仍偏普通新闻，就进入 story/theme 精排护栏；如果 coverage 仍低，就需要实现真实低频社区/搜索 probe provider。

2026-06-08 `DiscussionProbeProvider v1` 实施：

- 新增 `discussion_probe_provider.py`，对 `discussion_probe_requests.json` 中的公开搜索入口做可选低频观测。
- 新增产物 `discussion_probe_observations.json`，记录每个平台搜索目标的 `ok/blocked/error/skipped_manual`、状态码、结果标题、结果数、关键词命中和讨论提示数。
- CLI 新增 `--run-discussion-probe-provider` 和 `--discussion-probe-provider-platform-limit`。默认关闭，避免每轮都访问社区/搜索平台。
- `build_discussion_probe_report` 现在会同时合并正文讨论证据和 provider 观测证据。单平台弱结果不会提升候选；多平台命中或明显评论/转发/讨论提示才会进入 `discussed`。
- story 精排继续使用“有效讨论分”护栏：无讨论证据的平台词不再抬高故事排名，避免把 Steam 店铺页或页面页脚误判成热点。
- 下一步评估重点从“能否生成入口”转为“真实 provider observations 是否能证明热点”：如果 `with_result_signal` 仍低，先研究搜索页 blocked/JS 空壳/查询词问题；如果信号变多但误报高，继续收紧 provider 评分阈值。

2026-06-08 `SearchExpansion v0` 实施：

- 路线修正：不继续深挖热度探针评分，先扩大候选发现面；热度探针保持保守，用于后续确认讨论证据。
- 新增 `search_expansion.py`，根据 `source_theme_counts.json` 的主题缺口生成短查询，并低频观测公开搜索页。
- 新增 LangGraph 节点 `expand_search_candidates`，位置在 `search_candidates` 之后、`fetch_documents` 之前。
- 新增产物 `search_expansion_requests.json`、`search_expansion_observations.json`、`search_expansion_candidates.json`。
- CLI 新增 `--run-search-expansion`、`--search-expansion-limit`、`--search-expansion-platform-limit`。默认关闭；启用后有效搜索结果只追加为 supplemental 候选线索。
- `discussion_search_lead` 只作为线索进入候选池；进入 claim extraction 后标为 `search_lead`，规则核查默认拒绝发布，避免搜索页标题被当成事实新闻。
- LLM 下一步接入点不是“判断热度”，而是 query 压缩、游戏名/厂商名别名扩展、搜索结果相关性分类和去重辅助。
- 下一轮真实评估应看：新增 supplemental 线索数量、主题缺口是否改善、无关结果比例、重复率、blocked/error、以及这些线索经 DiscussionProbe 后是否能转化为真实热点证据。

2026-06-08 `SearchExpansion v0.1` 实施：

- SearchExpansion 改为多方法扩展：`theme_gap` 负责主题缺口补搜，`candidate_followup` 负责对当前候选做社区跟进搜索，`event_burst` 负责游戏展/发布会/直面会等爆发日专项搜索，`new_content_watch` 负责爆发日的新作、新预告、发售日、试玩反馈等通用新内容查询。
- 新增 `event_context` 识别：从当前候选标题/摘要中寻找 Showcase、Direct、Summer Game Fest、Xbox Games Showcase、发布会、游戏展等事件词，以及 reveal、trailer、release date、demo、新作、预告、发售日等新内容词。
- 爆发日候选带 `quota_policy=event_burst_briefing_candidate` 和 `allow_briefing_overflow=true`，表示它们可以突破日常简讯候选发现上限，但仍只是 `discussion_search_lead`，不能绕过事实核查。
- LangGraph 节点 `expand_search_candidates` 已把当前 main/supplemental 候选传给 SearchExpansion，因此真实运行时可以根据当天候选自动判断是否需要发布会/游戏展专项扩展。
- 运行进度会输出 SearchExpansion 方法分布，方便判断本轮是主题补缺、候选跟进还是爆发日逻辑在起作用。
- 下一轮优化重点：用 LLM 做 query 压缩、游戏名/厂商名别名扩展、搜索结果相关性分类；同时评估 `event_burst` 是否真的带来了高热度新内容，而不是普通发布会汇总。

2026-06-12 `boundary_guard_live` 复盘与 Agent 雏形：

- 本轮 7 个真实来源中 6 个 healthy、1 个 needs_fill；raw 约 747，accepted 473，main 228，supplemental 245，主题候选池接近 100，但旧版全局 10 条最终 story 仍被游民星空主导，其中约 7 条来自中文单源，英文来源约 3 条。
- 边界保护已开始生效：20 个取证候选里 19 个为 `candidate_url` 证据，1 个 GameSpot 403 降级为 `retrieved_context`；`supplemental_context_not_publishable` 拒绝了 5 条补充上下文，说明“相似上下文不能当候选正文证据发布”的边界成立。
- 仍暴露两个 Phase 4.5 阻塞点：讨论热度证据覆盖不足，且公司名/人物名会造成伪相关，例如“比尔盖茨/爱泼斯坦”被误归到微软主题。该类问题不能长期靠无限堆关键词解决，应进入“确定性护栏 + LLM/人工判断请求”的工程化形态。
- 已新增 `editorial_judgment.py` 和 `editorial_judgment_requests.json`：`score_heat` 会对高风险或模糊候选生成 `EditorialJudgmentAgent` 请求包。这个 Agent 只判断游戏相关性、热度是否属于游戏讨论、是否可发布；它不新增事实、不核查事实真假、不发明来源，也暂不改变最终排序。
- `stories.json` 顶层补充 `url`、`source_id`、`candidate_type`、`candidate_lane`、`score`、`heat_score`，后续人工评分、质量报告和 Agent 判断不再只能从 claim metadata 里追踪来源。
- 进入真正 multi-agent 的原则：当某层确定性方法已经能够稳定暴露“为什么失败、缺什么、风险在哪里”，但继续细化会变成大量 brittle 规则时，才把该层升级为 Agent 判断调用。Agent 的输入必须是结构化 artifact，输出必须是 JSON 决策，不允许直接改写事实链路。
- 下一步优化方向：
  - 将 `EditorialJudgmentAgent` 先用于人工/LLM 对照评估，观察它能否稳定识别公司名伪相关、泛娱乐热度、泛科技热度和弱游戏关联内容。
  - 补充 story/theme 精排护栏：单源上限、主题均衡、讨论证据优先、弱证据英文 fallback 标记。
  - 继续提高 DiscussionProbe 的有效讨论信号，而不是只看媒体标题热度。
  - 等 Agent 请求包稳定后，再增加可选 CLI 开关，例如 `--run-editorial-judgment-agent`，将 LLM 判断结果以“降权/待审/拒绝建议”方式进入 story selection。

2026-06-12 Phase 4.5 目标澄清：社交热度、语义核查与主题精排：

- 对“讨论热度证据弱”的判断：这不是单纯评分公式问题，而是社交属性平台尚未真正接入的问题。Bilibili、微博、贴吧、小黑盒、Reddit、YouTube、Steam、X 等平台应作为 `SocialHeatProvider` / `DiscussionProbeProvider` 的后续实现目标。第一阶段只保留可审计接口：公开搜索、人工导入、浏览器低频 sidecar、未来 API/第三方搜索服务。它们只证明“是否正在讨论”，不证明事实真假。
- 对“游民星空单源主导”的判断：需要先做 `SourceDominanceAudit`，区分三种情况：
  - 游民星空确实在 48h 内覆盖更多中文游戏新闻，且文章/评论区/转载能提供真实互动证据。这种情况可以保留较高权重，但仍要受单源上限和主题均衡约束。
  - 游民星空只是标题中有“热议/全网/玩家”等词，或站内评论提示被当成热度。这种情况应把它降为媒体新鲜度，不能当社区热度。
  - 游民星空混入泛娱乐、社会、科技、带货内容。这类内容应在归类门进入 supplemental/reject，不能等最终精排才处理。
- 对“LLM/人工语义核查”的判断：适合做成可审计的两层流程。
  - LLM 层：`VerificationAgent` 判断 claim 与证据是否匹配，`EditorialJudgmentAgent` 判断是否游戏相关/是否可发布，`RelevanceClassifierAgent` 判断搜索结果是否同一事件，`RerankAgent` 解释主题内排序。LLM 输出只能是 JSON 决策和理由，不允许新增事实、URL 或证据。
  - 人工层：`content_review.md` 和 `human_review_template.json` 继续作为人工评分入口，后续新增 `human_semantic_review.json`，记录 `game_relevance`、`same_event`、`heat_validity`、`publishability`、`style_fit`、`review_notes`。这些人工标签用于校准 prompt、权重和测试样例，而不是每次都手动改代码。
- 对“非游戏新闻混进最终 story”的判断：应同时治理归类和精排，但职责不同。
  - 归类阶段负责硬门：明显社会新闻、娱乐八卦、泛科技、折扣、攻略、营销活动进入 supplemental/reject；模糊项进入 `editorial_judgment_requests.json`。
  - 精排阶段负责选择：先在五个主题板块内分别排序，每板块最多 20 条 story 候选；再在每个板块内最多选 10 条最终 story，并加入单源上限、板块内内容类型配比、讨论证据优先、弱证据降权和 off-topic risk 降权。不能把所有候选混在一个全局排行榜里直接取前 10。
- 对 Agent 模式的判断：Phase 4.5 不应把整条流程改成 ReAct，也不应依赖 reflection 自我循环找热点。正确分工是：`SocialHeatProvider`、`SourceDominanceAudit`、`ThemeReranker` 作为 workflow 节点落盘；`AccessPlannerAgent` / `SourceRecoveryAgent` 用 bounded ReAct 选择白名单解析器和访问方式；`ContentQualityAgent` / 人工复盘用 reflection 对 artifact 打分、解释失败原因并提出下一轮动作。
- 对外部 Agent/LLM 工具链的判断：当前不替换 LangGraph 主流程，也不先引入大而全 Agent 框架。LangChain、Playwright、Crawl4AI、Firecrawl、搜索 API 等只作为局部 adapter/provider 接入；主流程仍以 artifact contract、测试和可复盘 JSON 为中心。第一批社交热度接入先试无需登录的公开入口，普通 HTTP 可用的平台优先；需要登录、JS 或 App 的平台先标记为 `browser_sidecar`、`manual_import` 或 `api_or_search_service`。
- 2026-06-13 无登录平台探测结论：`bilibili` 与 `steam_discussions` 适合作为第一批 public_search provider；`youtube`、`x` 更适合作为 browser sidecar/搜索服务候选；`weibo` 返回 Visitor System，`tieba`/`reddit` 容易 403，`xiaoheihe` 暂走 manual import。该结论只决定接入方式，不把搜索页当事实证据。
- 2026-06-13 实施状态：已新增 `social_heat.py`，统一 `social_heat_observations.json` 的 observation schema、summary 和平台 access profile；`probe_discussions` 会持久化该 artifact；`score_heat` 会额外写出 `source_dominance_audit.json`，解释单源主导原因但不改变排序；`content_review.md` 会展示社交热度观测与单源主导诊断，便于人工评分。
- 2026-06-13 社交相关性门实施状态：已新增 `social_heat_relevance.py`，在 `probe_discussions` 后写出 `social_heat_relevance_checks.json`、`semantic_relevance_requests.json` 和 `semantic_relevance_results.json`。当前只做确定性相关性检查和语义复核请求生成，不直接提高 story 排名；`content_review.md` 会展示检查总数、相关性分布、时间提示、结果类型和语义复核候选数量。
- 2026-06-13 新边界：`heat_validity_hint=game_discussion` 只表示搜索结果有游戏圈语境，不代表同一事件已命中。Bilibili public search 可用，但会返回同关键词不同事件；下一步必须引入 `same_event/same_game/within_48h` 相关性分类，才能把 observation 用作排序加分。
- 2026-06-14 `social_heat_relevance_live` 复盘：本轮 `social_heat_observations.json` 有 40 条观测，Bilibili 20、微博 20，全部 `ok`；但 `social_heat_relevance_checks.json` 中 `off_topic=35`、`same_platform_only=5`、`semantic_review_candidates=0`。这说明 provider 访问链路已经能跑通，但候选标题和搜索 query 仍然过宽，微博没有可用时间提示，Bilibili 能找到游戏语境却很少命中同一事件。当前不应急着把 `semantic_relevance_requests.json` 接给 LLM；应先调候选进入 probe 的过滤、query 压缩、平台排序和 Bilibili/Steam provider。
- 2026-06-14 采集后选择复盘：`social_heat_relevance_live` 中任天堂并不是爬取不足，`source_theme_counts.json` 显示任天堂主候选约 31 条，`theme_candidate_pool.json` 中任天堂 `candidate_count=34`、`pool_count=20`；当时真正断点是 `--document-fetch-limit 20` 被五个板块均分，任天堂只 `fetch_selected_count=4`，后续只能生成 3 条 `story_candidates`。已将正文取证修正为“先按板块拆分，再按每板块预算取证和评估”：`--document-fetch-limit 20` 现在表示每个板块最多抓 20 条正文。`ThemeFetchBackfill` 保留为异常保险，只在某板块候选不足、正文抓取失败或 story 转化不足时触发。
- 2026-06-15 Story Mix Policy 修正：旧版 `build_thematic_story_selection` 会把五个板块候选混合后再取全局 10 条，容易让补充板块或单一高热来源挤掉平台板块。现已改为 `per_section_limit=20` 形成板块内 story 候选池，再用 `final_per_section_limit=10` 为每个板块单独选择最终 story；`stories.json` 总量可以超过 10，`theme_sections.json` 会记录 `final_limit_scope=per_section`、`selection_scope=per_section` 和每板块 `selected_count`。
- 2026-06-15 `story_mix_policy_live` 复盘：本轮 `theme_candidate_pool=95`、`fetch_selected=79`、`documents=76`、`story_candidates=58`、`final_stories=45`，说明“每板块最多 10 条最终 story”已生效。任天堂板块 `candidate_count=11`、`selected_count=10`，数量不是主要瓶颈；真正问题是板块内排序仍会让广告擦边、拍卖、法律纠纷、个人感悟等 `platform_business/personal_or_sentiment` 内容排在游戏本体新闻前面。
- 本轮具体暴露的游戏本体问题：
  - 《艾尔登法环褪色者版》NS2 预购/容量新闻已进入 `theme_candidate_pool` 的任天堂板块，且 `editorial_intent=core_game_update`，但最终展示时出现在补充板块。这说明从 candidate/context/claim 到 story 的链路中，候选阶段的 `theme_section/source_entry_themes/editorial_intent` 没有稳定传递到 story classification。
  - 《节奏天国：奇迹之星》《异度之刃》《轨道双子星》等确实被抓到，但发布时间多为 2026-06-12 或更早，在本轮 48h 窗口内被标为 `outside_time_window`。这不是爬虫没抓到，而是“游戏节/直面会余波”与严格 48h 主新闻之间缺一个 `event_window_context` 层。
  - 任天堂最终 Top 10 中仍出现“低俗广告文案”“马里奥卡带拍卖”“幻兽帕鲁法律赔偿”“横尾太郎 NS2 没拆封”等内容。它们可以作为补充或单条趣闻，但不应稳定压过发售日、预购、试玩、容量、性能、DLC、新设定等游戏本体更新。
- 因此下一步优先级调整：先做 `ThemeSectionCarryover + CoreGameStoryPolicy/ThemeReranker v1`，再做 `CandidateDedup v1/StoryClusterer v1`。去重仍重要，但在本轮样本里，更先暴露的是“同板块内什么内容应该靠前”的编辑策略问题。
- 当前执行顺序（2026-06-15，结合 `story_mix_policy_live` 与 `claudeCheck.md`）：
  1. `ThemeSectionCarryover`：把 candidate 阶段的 `theme_section`、`source_entry_themes`、`editorial_intent`、`candidate_lane` 可靠传入 context pack、claim、story，避免老头环 NS2 这类任天堂游戏本体新闻在 story 阶段掉到补充板块。MVP 已完成：`context_packs`、`claims.metadata`、`story_candidates/stories` 会保留主题候选、来源板块和编辑意图字段。
  2. `CoreGameStoryPolicy / ThemeReranker v1`：每板块优先保留 `core_game_announcement`、`core_game_update`、`game_detail_update`、`release_or_preorder`、`performance_or_platform_version`；对 `platform_business/legal_controversy/auction/personal_sentiment/advertising_controversy` 设置轻量软加权，不直接覆盖热度/证据分。
  3. `EditorialJudgmentAgent MVP`：暂缓实现。后续进入全面智能化设计时，再补 `editorial_judgment.md` prompt、CLI flag、LLM 调用与结果 artifact；先只输出语义判断、降权/待审/拒绝建议，不直接新增事实。
  4. `theme_story_ranking_diagnostics.json`：解释每板块 Top 20 的排序理由、加权项、被挤掉原因和内容类型，供 `content_review.md` 人工复盘。
  5. `ImportantRejectedCandidatesDiagnostics / EventWindowContext`：把 48h 外但与游戏节、直面会、发布会强相关的游戏本体新闻记录为上下文候选；只有当 48h 内出现新进展、热度重新升温或官方补充时，才允许作为 `follow_up_update` 回到主流程。
  6. `ContentQualityGate conditional edge`：当 `gate_status=blocked` 时停止后续 layout/render 产物；`needs_review/pass` 才继续写人工评审包和后续包。
  7. `HttpFetcher retry/backoff`：补 3 次重试、指数退避、`Retry-After` 和 per-domain cooldown，降低繁忙新闻日的假性采集失败。
  8. `LlmRouter task_type`：让 editorial judgment、semantic relevance、claim verification、story clustering 使用不同模型/温度/token 上限。
  9. `CandidateDedup v1 / StoryClusterer v1`：在游戏相关内容基本筛干净后，再做去重和连续事件聚合。
  10. 等上述项能在 live run 中解释并减少误入选后，再讨论 Phase 5 排版成图。

### 2026-06-15 claudeCheck 建议分级

`claudeCheck.md` 的总体判断有价值：当前系统已经有采集、证据、评分和 artifact 基础，但真正阻塞内容质量的不是继续扩 RSS，而是语义判断、主题内精排、质量门分支和工程可验证性。结合 `story_mix_policy_live` 的结果，建议分为三类处理。

#### 可现在加入计划

这些建议与当前 Phase 4.555/4.56 直接相关，投入小或能立刻改善内容质量。

1. `EditorialJudgmentAgent` 执行路径
   - 采纳方向：设计保留，暂缓执行；等进入全面智能化阶段再接入。
   - 原因：request builder 和 parser 已存在，但当前优先级是先把确定性链路、板块内规则精排和人工可读评审稳定下来。过早加入 LLM/agent/RAG 会产生大量只供模型消费的字段，对当前人工判断帮助有限。
   - 后续边界：只对每板块 Top 20 story candidates 或高风险候选调用；输出只影响 `editorial_judgment_result`、降权/待审/拒绝建议和 ranking diagnostics，不新增事实。

2. `ThemeSectionCarryover`
   - 采纳方向：现在加入计划，优先于复杂 RAG/去重。
   - 原因：《艾尔登法环褪色者版》NS2 预购/容量在候选阶段属于 Gamersky NS 且 `core_game_update`，但 story 阶段可能掉入 supplemental。必须先保证 candidate/context/claim/story 的主题与编辑意图连续。

3. `CoreGameStoryPolicy / ThemeReranker v1`
   - 采纳方向：现在加入计划。
   - 原因：Story Mix Policy 已把最终上限改成每板块最多 10 条，下一步瓶颈变成板块内排序。游戏本体更新应稳定高于拍卖、广告争议、个人感悟和纯法律纠纷。
   - 近期产物：`theme_story_ranking_diagnostics.json`，解释每板块 Top 20 的排序理由、内容类型、加权项和被挤掉原因。

4. `ContentQualityGate` 条件边
   - 采纳方向：现在加入计划，但作为低风险工程修复排在语义精排之后或同批。
   - 原因：当 `gate_status=blocked` 时继续生成 layout/render queue 没意义。应使用 LangGraph conditional edge：blocked 时停止在 review/quality 产物，`needs_review/pass` 才继续生成后续包。当前 Phase 5 本来也暂缓，修这项能让主流程更诚实。

5. `HttpFetcher` retry/backoff/domain cooldown
   - 采纳方向：现在加入计划，作为采集稳定性修复。
   - 原因：真实新闻高峰日会遇到 429、瞬时 DNS/连接问题或 WAF 限流。3 次重试、指数退避、`Retry-After` 和 per-domain cooldown 不改变事实链路，但能减少假性 source failure。

6. `LlmRouter / task_type model config`
   - 采纳方向：现在加入计划的轻量版。
   - 原因：query compression、editorial judgment、claim verification、story clustering 不应共用同一 max_tokens/temperature/model。先在 `load_llm_config(task_type=...)` 做最小路由，不急着引入复杂框架。

7. 缺失 prompt 的最小补齐
   - 采纳方向：现在只补最需要的 prompt。
   - 近期顺序：`editorial_judgment.md`、`semantic_relevance.md`、`story_clusterer.md`。
   - 暂不优先：`markdown_editor.md`、`platform_writer.md`、`historical_context_miner.md`，因为当前展示层和历史调味剂不是 Phase 4.5 阻塞点。

8. `ImportantRejectedCandidatesDiagnostics / EventWindowContext`
   - 采纳方向：现在加入计划，但默认只生成诊断 artifact。
   - 原因：《节奏天国》《异度之刃》《轨道双子星》被抓到但因 48h 窗口拒绝。它们不应直接进主新闻，但应进入发布会/直面会余波上下文，供后续 `follow_up_update` 判断。

9. 最小集成测试
   - 采纳方向：现在加入计划。
   - 原因：每次修改 story selection、theme carryover、quality gate 都会影响多个下游 artifact，应增加 dry-run graph/integration 测试和 regression fixture，避免只靠人工看 `briefing.md`。

#### 后续可进行的计划

这些建议是正确方向，但不应打断当前 Phase 4.555 的内容质量主线。

1. Pydantic runtime validation 渐进接入
   - 后续做。先从 `EvidenceChunk`、`ContextPack`、`ClaimVerification`、`SearchCandidate` 四类稳定 artifact 开始。
   - 原因：claudeCheck 对 `TypedDict(total=False)` 和 dict shape 漂移的批评成立，但全量替换会牵动太大。短期可以在新模块边界做 model_validate/model_dump。

2. `ArtifactManifest` / write-once artifact store
   - 兼容式第一版已做，完整迁移后续做。
   - 当前状态：`organize_artifacts` 会在主流程末尾生成 `artifacts_by_stage/` 镜像目录和 `artifact_manifest.json`，便于人工/Agent 按阶段读取。
   - 后续原因：多个节点覆盖同名 JSON 的问题真实存在，但真正的 write-once artifact store 会牵动所有节点读写路径。等 Phase 4.555 稳定后，再把 `context_packs.json` 等改成 stage-specific artifact + final alias，并让阶段目录成为主读写路径。

3. `PipelineState` 分层 TypedDict
   - 后续做。
   - 原因：有利于类型检查和维护，但运行行为不变，短期不解决“游戏本体新闻被挤掉”。

4. `nodes.py` 拆分为 `nodes/` 包
   - 后续做。
   - 原因：可维护性收益高，但属于结构重构。应等当前几个排序/语义节点接口稳定后再拆，避免反复搬动同一代码。

5. 技能化 skill contract / 11 个独立 skill
   - 后续做小步实验，不整体迁移。
   - 推荐第一个实验对象：`quality-gate` 或 `generate-briefing`，因为它们读 artifact、写 artifact、无网络副作用。
   - 原因：完全 skill 化是长期 multi-agent 能力展示点，但现在把采集、精排、验证全拆成 skill 会增加调试成本。

6. LangGraph parallel fan-out / checkpoint / human interrupt
   - 后续做。
   - 原因：`expand_search_candidates` 与 `probe_discussions`、`extract_claims` 与去重等确实可并行；但当前还没到性能瓶颈，先让 artifact 和语义判断正确。

7. SQLite evidence/memory store、向量库、RAG QA
   - 后续做。
   - 原因：当前 JSON memory 足够验证概念。RAG-2/RAG-3 要等 story lifecycle、human review labels 和 evidence schema 稳定后再上。

8. 30-60 天人工标注评估集、NDCG/MRR、prompt A/B
   - 后续做，进入 Phase 4.5 后半段。
   - 原因：当前已有 `content_review.md` 人工评分入口，但还没有稳定模型判断结果。等 EditorialJudgment/ThemeReranker 有输出后，再建立正式 eval harness。

9. 内容伦理、安全、版权和平台条款
   - 后续必须补。
   - 原因：发布前必须解决流言放大、平台 ToS、素材版权和敏感话题边界。但当前还没进入 Phase 5/6 自动排版发布，先记录为发布前硬门。

10. 部署、增量运行、冷启动、交付机制
   - 后续做。
   - 原因：这些决定产品化可用性，但当前 demo 还在内容质量验证阶段。等 Phase 4.5 通过后，再设计 cron、artifact retention、Docker、RSS/API/email/webhook 等交付能力。

#### 目前多余或暂不采纳的计划

这些不是永远无用，而是当前阶段投入产出比低，或会偏离“先把内容选对”的主线。

1. 立刻把整个 pipeline 改成 11 个独立 skills
   - 暂不采纳。
   - 原因：主流程仍在快速调整，尤其是 `ThemeSectionCarryover`、`ThemeReranker`、`StoryClusterer` 的数据契约还没稳定。过早拆成独立 skill 会让状态同步、测试和调试更困难。

2. 立刻把所有 dict 替换成 Pydantic 模型
   - 暂不采纳。
   - 原因：方向正确，但全量迁移会吞掉大量时间，并且容易引入字段兼容问题。当前只在新模块和关键 artifact 边界渐进验证。

3. 立刻引入完整 ArtifactStore/manifest 并重命名所有产物
   - 暂不采纳。
   - 原因：会影响现有人工评审路径、测试和用户熟悉的输出文件。先为新增诊断 artifact 使用清晰命名，后续再统一治理。

4. 立刻优化 Markdown/PlatformWriter prompt 或 CrewAI 创作 sidecar
   - 暂不采纳。
   - 原因：当前不是表达风格问题，而是入选 story 的语义质量和排序问题。写得更漂亮会掩盖筛选错误。

5. 立刻上 RAG QA / NewsQAAgent
   - 暂不采纳。
   - 原因：问答能力需要稳定 evidence store、story memory、人工标签和引用策略。现在上会把“内容未选对”的问题包装成问答能力，反而增加幻觉风险。

6. 立刻做内容交付/发布自动化
   - 暂不采纳。
   - 原因：Phase 5/6 已明确暂缓。内容质量未过关前，不应增加平台发布或运营自动化。

7. 立刻把所有采集换成 feedparser/Scrapy/Crawl4AI/Firecrawl
   - 暂不采纳。
   - 原因：当前采集数量已经足够暴露排序问题。局部 parser 可以继续优化，但不需要为了框架替换而重写采集层。

更新后的近期执行顺序：

1. `ThemeSectionCarryover`：修复候选主题和编辑意图在 story 阶段丢失。MVP 已完成，下一轮 live run 应重点观察《艾尔登法环褪色者版》这类来自 NS 板块的游戏本体新闻是否仍会掉入 supplemental。
2. `CoreGameStoryPolicy / ThemeReranker v1`：先做纯规则版板块内 story 排序。MVP 使用已有 `editorial_intent` 做轻量软加权，不新增大量机器字段，不接 LLM/RAG，不直接覆盖热度/证据评分。
3. `EditorialJudgmentAgent MVP`：暂缓到全面智能化阶段。届时再补 prompt、CLI flag、LLM 调用、结果 artifact，先只给建议/降权，不直接改事实。
4. `ImportantRejectedCandidatesDiagnostics / EventWindowContext`：记录 48h 外但重要的发布会余波候选。
5. `ContentQualityGate conditional edge` 与 `HttpFetcher retry/backoff`：补低风险工程护栏。
6. `CandidateDedup v1 / StoryClusterer v1`：在游戏相关内容基本筛干净后再做去重和连续事件聚合。

### Phase 4.55：采集后选择诊断与回填

目标：解决“爬到了很多，但没有进入最终 story”的问题。该阶段不继续扩源，而是检查候选从采集到 story 的转化率，并在某个板块不足时有控制地补抓正文。

2026-06-15 Artifact 分阶段组织：

- 当前先实现兼容式 `artifacts_by_stage/` 镜像目录：主流程仍保留根目录文件和现有 `*_path` 状态，最后由 `organize_artifacts` 节点把已生成产物复制到阶段目录，并输出 `artifact_manifest.json`。
- 第一版阶段目录包括：`source_collection`、`search_expansion`、`evidence_fetch`、`discussion_heat`、`asset_and_dedup`、`claim_verification`、`story_selection`、`platform_content`、`layout_render`。
- 人工可以从 `artifacts_by_stage/story_selection/theme_sections.json`、`artifacts_by_stage/platform_content/content_review.md` 等路径复盘；后续 Agent/LLM 也可以先读 `artifact_manifest.json` 再决定读取哪些阶段。
- 暂不一次性迁移所有节点的读写路径，避免打断现有测试和人工评审链接。等 artifact contract 稳定后，再把根目录产物降级为兼容层，阶段目录成为主读写路径。
- 运行复盘详见 `docs/experience.md#EXP-2026-06-15-02-ArtifactStage-与-DedupLive-对比`。

核心产物：

- `selection_stage_diagnostics.json`：按板块记录 `candidate_count`、`pool_count`、`fetch_selected_count`、`context_pack_count`、`claim_verification_count`、`story_candidate_count`、`final_selected_count` 和 `primary_bottleneck`。
- `selection_backfill_candidates.json`：当某板块 story 不足且瓶颈是 `document_fetch_budget` 时，列出需要补抓正文的候选。
- `docs/post_collection_selection_strategy.md`：记录本轮诊断经验、回填规则和 Agent retry policy。
- `docs/superpowers/plans/2026-06-14-post-collection-selection-backfill.md`：后续 TDD 实施计划。

2026-06-14 实施状态：

- `SelectionStageDiagnostics` 已接入 `score_heat`，用于解释每个板块从候选到最终 story 的数量损耗。
- `ThemeFetchBackfill` 第一版已接入为可选规划节点：传入 `--run-selection-backfill` 后写出 `selection_backfill_candidates.json`，但暂不自动二次抓正文、重跑 claim verification 和 story ranking。
- 当前 `--document-fetch-limit` 是每板块正文取证预算；当五个板块都有候选时，`20` 最多会形成约 100 条首轮正文取证候选，而不是每板块约 `4`。因此日常链路应先依靠板块内排序拿足候选，`backfill` 只处理异常缺口。
- 当前 `Story Mix Policy` 是每板块独立入选：`story_candidates` 先进入每板块最多 20 条的候选池，再由 `final_per_section_limit=10` 选出各板块最终 story；最终 `stories.json` 不再是全局 Top 10。
- 下一步若某板块在首轮每板块取证后仍不足，再实现真正的 `backfill_fetch_documents -> extract_claims -> verify_claims -> score_heat rerun`。
- 主题精排要补“游戏本体资讯优先”策略：新作/发售日/试玩/DLC/更新/实机/预告/评分解禁等应优先进入各板块；`NS2 吃灰`、个人感悟、泛情绪讨论和花边热点只能作为补充或单条代表，不能重复覆盖核心游戏新闻。

长期评估：

- 可以收集 30 天或 60 天候选作为离线测试集，尤其适合游戏节、发布会、直面会之后的爆发期。
- 长窗口数据只用于评估粗排、取证预算、主题回填、旧闻/后续更新识别和 Agent retry policy，不直接作为日常 48 小时 briefing。
- 推荐先用 `--lookback-hours 720` 和 `--lookback-hours 1440` 跑离线目录，确认每个板块从候选到 story 的转化率，再决定是否调整权重。

### Phase 4.555：主题内游戏本体优先与精排护栏

目标：解决 Story Mix Policy 生效后暴露的新问题：每个板块已经能拿到最多 10 条最终 story，但板块内部仍可能被平台争议、拍卖、个人感悟、广告擦边、法律纠纷等高讨论内容覆盖，导致发售日、预购、容量、试玩、性能、DLC、新设定、新作公布等游戏本体新闻位置偏低。

核心原则：

- `core_game_update` 高于泛平台话题。凡是直接包含新作公布、发售/预购、试玩、容量、性能、DLC、更新、实机、角色/设定、评分解禁、平台版本差异的内容，应获得主题内基础优先权。
- `platform_business/legal_controversy/auction/personal_sentiment/advertising_controversy` 不是不能入选，但每板块应有软上限；除非有强社交热度证据或官方/权威后续，否则不能连续占据多个名额。
- 候选阶段的 `theme_section/source_entry_themes/editorial_intent/candidate_lane` 必须传递到 context pack、claim、story。story 阶段不能只靠标题关键词重新猜板块，否则会把任天堂游戏本体新闻误归到补充板块。
- 社交热度只做放大器，不做唯一入选理由。没有同事件讨论证据的“热议/吐槽/网友称”类标题，不能靠标题热词压过游戏本体更新。

近期实现项：

1. `ThemeSectionCarryover`
   - 输入：`theme_candidate_pool.json`、`context_packs.json`、`claims.json`、`story_candidates.json`。
   - 输出：story 上稳定保留 `theme_section`、`theme_section_candidates`、`source_entry_themes`、`editorial_intent`、`candidate_lane`。
   - 当前状态：MVP 已完成。`context_packs` 会保留候选主题元数据；`claims.metadata` 会继续携带这些字段；`build_ranked_stories` 会把它们恢复到 story，并优先用已有 `theme_section` 做板块归属，再回退到关键词分类。
   - 编辑意图判定：当前先用 `editorial_focus.candidate_editorial_intent` 的确定性规则，根据 `candidate_type`、标题/摘要关键词、标签和来源板块信息归为 `core_game_update`、`core_game_report`、`platform_business`、`personal_or_sentiment`、`community_or_meme`、`general` 等轻量类别。后续 `EditorialJudgmentAgent MVP` 只做语义核查与建议，不直接改事实。
   - 验收：类似《艾尔登法环褪色者版》NS2 预购/容量这类来自 Gamersky NS 的游戏本体新闻，进入 story 后仍归到任天堂或对应多平台板块，而不是掉入 supplemental。

2. `CoreGameStoryPolicy v1`
   - 为 story 增加可解释的 `story_editorial_intent`，至少包含 `core_game_announcement`、`core_game_update`、`game_detail_update`、`release_or_preorder`、`performance_or_platform_version`、`platform_business`、`legal_controversy`、`community_sentiment`、`personal_or_sentiment`、`advertising_controversy`。
   - 在 `ThemeReranker` 中给予游戏本体更新基础加权；对个人感悟、拍卖、纯法律纠纷、广告文案争议设置板块内数量上限。
   - 当前状态：MVP 已完成轻量版。`build_thematic_story_selection` 不改变原始 `story_score`，只在板块内排序时按已有 `editorial_intent` 添加小幅软加权：游戏本体更新上浮，个人感悟/低价值花边下沉。
   - 2026-06-15 复盘结论：ThemeReranker 已能把《艾尔登法环褪色者版》这类 NS 板块游戏本体新闻拉回任天堂板块，但 `editorial_intent` 仍需要继续校准。详见 `docs/experience.md#EXP-2026-06-15-01-Story-Mix-与主题精排`。
   - 输出 `theme_story_ranking_diagnostics.json`，记录每个板块前 20 个 story 候选的分数构成、排序理由、被挤掉原因和内容类型。

3. `ImportantRejectedCandidatesDiagnostics`
   - 输出 `important_rejected_candidates.json`，记录被 `outside_time_window` 拒绝但属于游戏本体的候选，例如发布会/直面会后 48h 外的《节奏天国》《异度之刃》《轨道双子星》等。
   - 这些内容默认不进入 48h 主新闻，但可进入 `event_window_context_candidates.json`，作为“游戏节余波”“发布会背景”“后续更新识别”的候选上下文。

4. `EventWindowContext`
   - 严格 48h 仍是主线 hard gate。
   - 对游戏节、直面会、发布会、厂商直播等事件，可保留 72-96h 的上下文窗口，但只有满足 `follow_up_update`、`official_confirmation`、`new_detail_after_announcement`、`social_heat_reactivation` 时才回到主 story 流程。
   - 低热度或无新进展的旧发布会内容只作为背景，不占用每板块 10 条最终 story 名额。

成功标准：

- 任天堂板块中，发售/预购/试玩/容量/性能/新设定类内容优先级明显高于拍卖、广告争议、个人感悟。
- 每个板块的 `content_review.md` 能解释“为什么这条游戏本体新闻入选/没入选”。
- `selection_stage_diagnostics.json` 不只告诉我们数量掉在哪里，还能通过 `theme_story_ranking_diagnostics.json` 告诉我们质量和排序为什么偏。

### Phase 4.56：去重、事件聚合与连续报道合并

目标：解决“同一新闻被多个媒体重复转载”和“同一发布事件连续爆出多个新信息”这两类不同问题。前者应合并降重，后者应聚合成一条更完整的 story 或事件时间线，而不是误删。

推荐位置：

```text
search_candidates
 -> candidate_type/theme classification
 -> CandidateDedup
 -> theme_candidate_pool
 -> fetch_documents
 -> EvidenceMerge
 -> claim extraction / verification
 -> StoryClusterer
 -> ThemeReranker
 -> final stories
```

近期先做 `CandidateDedup v1`：

- 输入：`candidates.json`、`supplemental_candidates.json`、`theme_candidate_pool.json`。
- 输出：`candidate_clusters.json`、`deduped_theme_candidate_pool.json`、`dedup_diagnostics.json`。
- 方法：先用确定性规则，不接向量库。规则包括 canonical URL、去参数 URL、标题规范化、实体重合、游戏名/平台名、发布时间接近、来源类型、板块归类一致性。
- 作用：减少重复抓正文、重复验证和重复评分，但不删除证据来源；被合并的 URL 进入 `merged_source_urls`。
- 不做：不凭标题相似就判定“同一事件”，不把跨语言相似标题直接合并，不丢弃官方源或一手源。

2026-06-15 MVP 状态：

- 已实现第一版 `annotate_story_clusters` 保守聚合：同一 canonical URL（去 query/fragment）、规范化标题完全一致/高度确定一致、以及少量明确已知规则会合并到同一个 `story_cluster_id`。
- 已新增 `dedup_semantic_review_requests.json`：同游戏/同实体但标题明显指向不同细节的内容，不在确定性阶段直接合并，而是输出给未来 `StoryClusterReviewAgent` 或人工判断。
- 第一版只做“明显重复”合并，不做模糊相似度阈值、不做跨语言语义合并、不做 RAG 历史判断，避免在没有 LLM/RAG 参与时误删连续报道。
- `artifacts_by_stage/asset_and_dedup/` 会包含 `story_clusters.json` 和 `dedup_semantic_review_requests.json`，供人工、Agent 和后续 SQL/RAG ingest 使用。
- `dedup_live` 对比显示本轮没有明显重复可合并，`dedup_semantic_review_requests` 为空；这说明下一步不应继续加重 dedup 规则，而应先做运行追踪、来源健康记录和 SQLite mirror。详见 `docs/experience.md#EXP-2026-06-15-02-ArtifactStage-与-DedupLive-对比`。

中期做 `StoryClusterer v1`：

- 输入：`context_packs.json`、`claims.json`、`claim_verifications.json`、`social_heat_observations.json`、后续的记忆库/RAG 结果。
- 输出：`story_clusters.json`、`event_timelines.json`、`dedup_semantic_review_requests.json`。
- `cluster_role` 至少包含：
  - `primary_event`：同一事件的主报道。
  - `duplicate_report`：重复转载或轻微改写，默认不重复进入最终 story。
  - `new_detail_after_announcement`：同一事件的新设定、新预告、新角色、新平台、新日期等，应进入同一 story 的补充段或时间线。
  - `official_confirmation`：官方确认、辟谣或补充，优先级高于媒体复述。
  - `reaction_or_commentary`：玩家反应、媒体评论、主播/社区二创，适合补充板块或热度说明。
  - `late_repost`：事件首次出现早于 48 小时，当前只是晚发复述，默认降权或拒绝。
- 示例：发布会先公布某游戏发售时间，随后官博/X 又公布主角设定。这不是重复新闻，应聚合为同一事件下的新 detail；如果只是另一家媒体复述同一个发售日，则是 `duplicate_report`。

RAG/LLM 加入时机：

- 2026-06-15 决策：当前阶段先不实现分词、检索、语义判断、向量库或 LLM 事件查重字段。这些字段主要服务程序和模型，对当前人工内容判断帮助有限，容易让 artifact 变重。先把设计逻辑保存在 roadmap；等进入全面智能化阶段，再统一设计 Agent/RAG/LLM 的输入输出合同。
- 典型案例：游民星空 NS 板块 2026-06-15 与 2026-06-11 的《艾尔登法环》预售新闻可能属于同一事件复述。未来应由 `EventMemory + SemanticDuplicateJudge` 判断它是 `duplicate_report`、`late_repost`、`follow_up_update` 还是 `new_detail_after_announcement`；如果没有新增售价、容量、特典、地区、平台、官方说明等事实，则不应再次占据最终 story 名额。
- `CandidateDedup v1` 先不用 LLM，保持低成本、可解释、可回放。
- 当规则无法判断“重复转载”还是“连续补充”时，写入 `dedup_semantic_review_requests.json`，让 LLM/人工判断 `same_event`、`same_game`、`new_detail`、`duplicate_report`、`unrelated`。
- `RAG-1.5 event clustering support`：在 claim-level retrieval 稳定后，把同游戏、同实体、同时间窗、同发布会/直播/官方账号的证据片段检索出来，辅助 `StoryClusterer` 判断事件关系。
- `RAG-2 persistent memory retrieval`：用于识别旧闻复读、48 小时外首发但今日有新变化、系列历史背景、流言被官宣/辟谣的后续链。
- LLM 只能输出结构化判断和理由，不能凭空新增事实、URL、时间或证据；所有聚合理由必须回链到候选、claim 或 evidence id。

下一步顺序：

1. `RunTrace v0`：记录运行、节点、来源抓取、artifact 写入、阶段指标和错误，先写 JSONL。
2. `SQLiteMirror v0`：把已落盘 artifact ingest 成查询索引，不替代 JSON。
3. `EvidenceRetriever v1`：基于 SQLite FTS/BM25 + metadata filter 返回证据包。
4. `StoryClusterReviewAgent`：只处理 `dedup_semantic_review_requests.json`，输出建议，不直接改最终 story。

### Phase 4.57：SQL / RAG / LLM / Agent / Skill 接口化蓝图

目标：在确定性工程足够稳定后，先建立智能化接口和 artifact contract，再逐步接入 SQL、RAG、LLM、Agent 和项目专用 skills。该阶段不是把所有节点重写成 Agent，而是把已经稳定的 workflow 节点改造成可被 LangChain/LangGraph 组件复用的工具边界。

2026-06-15 路线修正：

- 下一步不应直接上 LangSmith，也不应直接让 LLM 判断新闻真假。先把联网失败、来源健康、运行参数、artifact 写入、候选选择和阶段评分完整追踪起来。
- SQL 先作为事件库和镜像索引层，JSON artifact 仍是当前主输出。目标是支撑旧闻/重复/后续更新判断，而不是立刻替换现有文件流。
- “联网失败智能化”分两层：确定性 `SourceReliability` 先做 retry/backoff/cooldown；当重试耗尽或来源表现异常时，再让 `SourceRecoveryAgent` 读取 trace 和诊断 artifact，提出可审计的恢复动作。
- 后续 issue 不再只用数字编号，而按 roadmap 的功能层维护：`RUN`、`COL`、`SRC`、`FIL`、`EVI`、`HEAT`、`CLU`、`VER`、`RANK`、`GEN`、`LAY`、`OPS`、`MEM`、`AG`。每个 issue 必须绑定 artifact contract、harness case 与用户通知策略；全局索引见 `docs/issues.md`，harness fixture 放在 `LangGraph/harness/<layer>/`。
- 未知异常采用“可追踪通知”而不是静默失败：确定性工具先重试，Agent/LLM 判断无合适工具时输出 `needs_user_action`，LangGraph 把该状态写入 `user_notifications.json` 并在后续 human review/recovery branch 中处理。
- 详细经验见 `docs/experience.md#EXP-2026-06-15-04-SQL-事件库联网失败与智能化第一步`。

2026-06-16 实现审计修正：

- 当前 `RunTrace`、`SQLiteMirror`、`EventStore`、`EvidenceRetriever`、`SearchIntelligence`、`SourceRecoveryAgent` 和 `StoryClusterReviewAgent` 已有 MVP/scaffold，但很多能力仍是 `flagged_node`、`shadow_mode` 或 `offline_tool`，不能写成已经接管主流程的智能体。
- 已把容易后续调参的判断阈值从分支内部抽成 policy：`SourceRecoveryPolicy` 管理恢复阈值、重试、回填、浏览器探针和缓存参数；`SearchRelevancePolicy` 管理搜索结果相关性阈值与默认 lookback，并允许直接传入搜索结果自己的 `published_at/observed_at`。
- 文档和代码命名必须以实际模块为准：热度合同在 `social_heat.py`，流言分级与因果拆分在 `evidence_verification.py`，历史重复判断当前在 `event_timeline.py` 与 SQL event store 设计中；不要提前引用尚不存在的拆分模块。
- 进入 LangChain/LLM 前，先完成 artifact/schema 与 SQL/RAG 可回放边界；LangChain 作为节点内部 adapter，不替代 LangGraph workflow。LLM 第一批只做 shadow：query compression、search relevance、story cluster review、editorial judgment，不直接改最终 story。
- `docs/issues.md` 已补充每个功能层的目标结果、最低验收标准和测试焦点。后续新增 issue、harness 或测试时，必须先说明它服务哪个层级目标，避免只以“脚本跑通”作为完成标准。

LangChain 式设计原则：

- `LangGraph` 继续作为主流程编排层：负责状态、节点顺序、条件边、检查点、重试和人工复盘入口。
- `LangChain` 放在节点内部：用于 tool schema、retriever、document/chunk 表示、structured output parser、LLM runnable、batch 调用和缓存。
- `Tool` 只包装确定性能力，例如 `FetchDocumentTool`、`SearchExpansionTool`、`SocialHeatProbeTool`、`EvidenceRetrieverTool`、`StoryClusterReviewTool`。工具输出必须是 JSON，不直接写最终事实。
- `Retriever` 负责从 SQL/FTS/vector store 中取证据，不负责决定事实真假；事实判断仍由 verifier 或人工/LLM review 节点完成。
- `Structured output` 是硬边界：LLM 输出只能进入 `*_requests.json` / `*_results.json` / `*_review.md` 这类可审计 artifact。

SQL artifact contract：

- 先保留 JSON 为主输出，SQLite 作为镜像索引层，避免重写当前流水线。
- 第一批表：`runs`、`artifacts`、`raw_sources`、`candidates`、`documents`、`evidence_chunks`、`claims`、`claim_verifications`、`story_candidates`、`stories`、`platform_posts`、`user_notifications`。后续再补 `sources`、`story_clusters`、`social_heat_observations`、`human_reviews` 与事件库表。
- 每条业务记录必须至少包含 `run_id` 和可查询核心字段；`artifact_path`、`source_id`、`url`、`observed_at`、`published_at`、`theme_section`、`schema_version` 按 artifact 类型逐步补齐。MVP 先通过 `artifacts` 表和各表 `raw_json` 保证可追溯，后续 `RUN-002` 再收紧 schema 校验。
- SQL 的第一目标不是生成内容，而是支持复盘、去重、旧闻/后续更新识别、长窗口离线评估和 RAG 检索。
- `candidate_memory.json` 不是完整原始库，它只是候选记忆：记录 URL/title key、first_seen_at、last_seen_at、seen_count、source_ids、published_at_values，用来辅助 `late_repost/follow_up_update`。完整 raw/intermediate/final story 历史应进入 SQLite mirror。
- 最终 story 需要保留发布生命周期字段：当前 `stories.publish_status` 默认 `unpublished`，`platform_posts.publish_status` 默认 `draft`；真正发布、回滚、失败、平台 ID 等运营状态留给 OPS 阶段更新。
- 2026-06-15 MVP 状态：`MEM-001 SQLiteMirror v0` 已实现离线 ingest 与命令入口，采用“核心查询字段 + raw_json”策略镜像当前 output_dir，不替代 JSON 主流程。
- 2026-06-16 MVP 状态：新增 `persistence/agent_query.py` 作为 Codex/Agent/FastAPI 的只读白名单查询入口，支持 `runs`、`summary`、`stories`、`candidates`、`notifications`、`artifacts`、`quality-flags`。后续默认不应让 Agent 扫输出目录或生成临时 SQL；需要更多视图时先扩展该查询合同。

RunTrace contract：

- 先新增 `run_manifest.json`、`run_events.jsonl` 与 `user_notifications.json`，不改变主流程决策。
- `run_manifest.json` 记录 `run_id`、启动参数、代码版本/配置摘要、输出目录、开始/结束时间、总体状态、阶段分数。
- `run_events.jsonl` 记录 `run_started`、`node_started`、`node_finished`、`source_fetch_finished`、`artifact_written`、`candidate_rejected`、`story_selected`、`llm_request_prepared`、`human_review_recorded` 等事件。
- `user_notifications.json` 记录需要用户查看的问题：爬取结构变化、所有恢复工具都不适合、LLM 返回格式无法修复、关键来源连续失败、blocking 级内容质量问题等。
- 每个 artifact 写入时记录 `artifact_key`、`path`、`stage`、`schema_version`、`record_count`、`size_bytes`、`sha256`，后续 SQLite/RAG/Agent 只读 manifest 和 artifact index，不扫目录猜文件。
- 运行追踪经验详见 `docs/experience.md#EXP-2026-06-15-03-SQL追踪与智能化入口`。
- 2026-06-15 MVP 状态：`RUN-001 RunTrace v0` 已接入 CLI streaming 层；当前记录 `run_started/node_finished/artifact_written/run_finished`、异常 blocking notification、artifact path/size/hash，并在运行结束后重新生成 staged artifact manifest。更细的 node_started、record_count、schema_version 与 conditional recovery branch 留给 `RUN-002/RUN-004`。

SourceReliability / retry contract：

- `HttpFetcher` 增加 retry/backoff/cooldown，但只对 transient errors 生效：timeout、connection reset、DNS/SSL transient、HTTP 429、HTTP 5xx。
- 默认 `max_attempts=3`；高优先级来源或无替代来源可配置到 `5`；404、明确 forbidden、URL 范围错误和 parser mismatch 不做盲目重试。
- 每次请求输出 attempt 级 metadata：`attempt_index`、`started_at`、`ended_at`、`status_code`、`error_type`、`retryable`、`will_retry`、`sleep_seconds`、`cooldown_until`。
- `collector_errors.json` 不只记录最后错误，还应记录 attempt summary，供 `source_health.json`、`run_events.jsonl`、SQLite 和后续 Agent 使用。
- LangGraph 节点级 retry 只用于会抛异常的 LLM/API/tool 节点；当前 collector 多数错误被转成 artifact，因此短期重点是 fetcher/collector 层 retry。
- 后续 LangChain 工具化时，把 `FetchDocumentTool`、`SearchProviderTool`、`SocialHeatProbeTool` 包成 Runnable，并用 `.with_retry()` 做工具级 transient retry。主事实判断仍由 LangGraph 状态机控制。
- 2026-06-15 MVP 状态：`COL-001 HttpFetcher Retry` 与 `COL-002 Collector Error Propagation` 已实现最小闭环；当前只做有限重试和 attempt 透传，source-level cooldown/fuse 与 `SourceRecoveryAgent` 仍放在后续。
- 2026-06-16 修复：游民星空 JSONP 列表存在 `title` 属性被引号截断的情况，曾导致最终微软 story 标题只剩 `Xbox将`。已在列表解析器增加短标题回填守卫，并在 claim extraction 增加“候选标题过短时从正文证据标题回填”的二道保险；后续 parser harness 应继续覆盖短标题、空正文和缺时间戳三类质量问题。

RAG artifact contract：

- `EvidenceRetriever` 输入：`claim_id/story_id/entity/theme/time_window/source_filters`。
- 输出：`retrieved_evidence_packs.json`，包含 chunk id、URL、发布时间、相关性分、同事件/同游戏/同来源提示、缺失说明。
- 第一版优先 SQLite FTS/BM25 + metadata filter；向量库只在跨语言、同义表达和历史相似事件需求稳定后接入。
- RAG 不负责发现热点，不替代社交热度 provider，不绕过登录平台，不凭空补事实。

LLM artifact contract：

- 每个 LLM 任务都有 `task_type`：`claim_verification`、`semantic_relevance`、`editorial_judgment`、`story_cluster_review`、`query_compression`、`release_date_normalization`。
- 每个任务分为 `*_requests.json`、`*_results.json`、`*_failures.json`，保留 prompt version、model、temperature、token budget、input artifact ids、output schema version。
- 默认只对 Top N、高风险、人工标记或确定性规则无法判断的样本调用，避免 token 成本失控。
- Prompt 统一由 `LangGraph/prompts/prompt_registry.json` 管理。节点不得直接硬编码 prompt 文件和 schema；必须通过 `prompt_id` 找到 prompt_file、input_artifacts、output_schema、fallback 和 harness cases。
- Prompt 输出解析失败、schema 不匹配、超时或拒答时，只写 `*_failures.json` 和 warning notification，并回退到 registry 声明的 deterministic fallback，不得把自然语言解释写进事实链路。

Agent artifact contract：

- 近期 Agent 不接管主流程，只做 bounded tool-calling：读取诊断 artifact，选择白名单工具，输出下一步建议或复核结果。
- `SourceRecoveryAgent`：当某源 blocked/needs_fill 时，读取 `collector_diagnostics.json` 和页面样本，建议调整入口、分页、时间戳回填或浏览器探针。
- `StoryClusterReviewAgent`：读取 `dedup_semantic_review_requests.json` + RAG evidence pack，判断 `duplicate_report`、`new_detail_after_announcement`、`official_confirmation`、`reaction_or_commentary`、`unrelated`。
- `ContentQualityAgent`：读取 `content_quality_report.json`、`source_dominance_audit.json`、`theme_sections.json`，输出下一轮调参/人工复核建议，不直接改 facts。

Skill 规划：

- 当前不把业务逻辑拆成 Codex skill；先沉淀项目内部 docs/specs/plans。
- 当某类工作重复出现 3 次以上，再抽成项目 skill，例如 `source-parser-debugging`、`artifact-audit`、`content-review-eval`、`llm-result-contract-review`。
- Skill 只固化工作方法和检查清单，不承载实时新闻事实、不替代数据库或 RAG。

近期落地步骤：

1. `RUN-005 ArtifactSchemaRegistry v0`：已完成 MVP。只校验关键 JSON artifact，跳过 `.jsonl`、Markdown 和未登记可选 artifact；schema validation 通知会写回 run trace，避免未来服务端读不到阻塞信息。
2. `PRM-001/002 PromptRegistry + failure contract v0`：已完成 MVP。registry loader、prompt 文件存在性检查、必需字段校验和 failure artifact 已具备；`editorial_judgment.md` 已补齐。
3. `MEM-001/002 SQL end-to-end check`：用一个真实 output_dir 验证 SQLite mirror + event store ingest，从 raw/intermediate/final story 到 publish lifecycle 都能查询；JSON 仍为主输出。
4. `MEM-003 HistoricalImport v0`：导入约 2000 条资讯或 30-60 天长窗口资讯，作为重复、旧闻、后续更新和同游戏不同事件的评估集。
5. `EVI-003 EvidenceRetriever v1`：基于 SQLite FTS/BM25 + metadata filter，为 claim/story 返回 `retrieved_evidence_packs.json`，先服务人工/LLM shadow review。
6. `LangChain adapter v0`：已完成 MVP。把 Fetch/Search/SocialHeat/EvidenceRetriever 包成可测试 tool/Runnable 形态，当前是项目原生 wrapper，不强依赖 LangChain 包；后续再接真正 LangChain Runnable/Tool 时沿用同一合同。
7. `LLM shadow tasks v0`：已完成 MVP。只对小样本启用 query compression、search relevance、story cluster review、editorial judgment；输出 JSON 建议与人工评审包，不直接改最终事实或排序。

`v020_fix_verify` 后的下一步顺序：

1. 稳定人工评审包：已由 `GEN-005` 完成 v0。`content_review.md` 和 `human_review_template.json` 不再被 story cluster review flag 跳过。
2. 收紧 LLM shadow 结构化输出：已由 `PRM-006/SHD-004` 完成 v0.1。2026-06-17 审查后按真实 prompt contract 校验 query compression、search relevance 和 editorial judgment。
3. 增加 warning notification：已由 `RUN-006` 完成 v0.1。source_broken、needs_fill、expected review pack missing、LLM fallback rate 过高都会写入 `user_notifications.json`，且 needs_fill 候选数读取真实 `accepted_count`。
4. 保持 SearchExpansion 为线索层：继续有效。Bilibili/Steam/搜索页结果只能证明“可能有人讨论”，必须经过 same_event/same_game/window 相关性分类和人工/LLM 复核后才参与热度加权。
5. 进入 FastAPI/Nuxt3 工作台 MVP：新增 `SVC` 功能层与 `LangGraph/harness/service_workbench/`，下一步实现 run 列表、artifact/stage 浏览、SQLite query、quality flags、source health、shadow 对比和人工评分入口；不做自动发布和平台登录。

### 0.2.0 版本目标：确定性工程 vs LLM 辅助对比

0.2.0 不以自动发布或排版成图为目标，而以“同一批游戏资讯输入下，可以稳定比较确定性主流程和 LLM 辅助 shadow 流程”为目标。

必须包含：

- 确定性主产物：`candidates.json`、`theme_candidate_pool.json`、`documents.json`、`evidence_chunks.json`、`claims.json`、`claim_verifications.json`、`stories.json`、`platform_posts.json`、`content_quality_report.json`。
- 追踪产物：`run_manifest.json`、`run_events.jsonl`、`user_notifications.json`、`artifact_manifest.json`、`schema_validation_report.json`。
- LLM shadow 产物：query compression、search relevance、editorial judgment、story cluster review 的 results/failures/report。
- 人工评审入口：能在 `content_review.md` 或后续工作台中看到 LLM 建议是否真正改善候选召回、误报过滤、主题路由和最终可读性。
- 服务化准备：FastAPI/Nuxt3 先做内部工作台，读取 run 和 artifact，不做自动发布、不做平台账号接入、不让 LLM 直接改事实链路。

LLM shadow 测试原则：

- 第一批只跑小样本，默认 `max_samples <= 5`。
- 每个任务必须有 positive、failure、boundary 样本。
- 评价指标不是“LLM 输出更像人话”，而是：query 是否更短更准、search result 是否减少伪相关、editorial judgment 是否把游戏本体新闻排到花边/泛娱乐之前、failure 是否安全回退。
- 所有 LLM 输出必须记录 token usage、prompt_id/version、model、fallback 和 input artifact refs。
- 2026-06-16 `v020_llm_shadow_smoke` 观察：确定性采集已能做到 5 个板块各 20 条 theme pool，正文抓取覆盖率约 91%；内容质量仍为 `needs_review`，主要短板是社交热度覆盖弱、单源主导、LLM/人工语义核查覆盖为 0。本轮还暴露 1 条 `documents.content` 为空的 schema invalid，已补正文为空时用候选标题/snippet 降级填充并标记 `content_fallback=candidate_text`。
- 同轮 shadow 结果：`query_compression` 5/5 成功，可作为第一批可用 LLM 辅助能力；`editorial_judgment` 1/5 成功、4/5 fallback 且 token 消耗高。已补 `llm_shadow.py` 输入压缩和 story/context pack URL 对齐，下一轮应重新验证 token、JSON 成功率和人工可用性；`search_relevance` 为 0 样本，不是模型失败，而是本轮 `search_expansion_candidates.json` 为空，需要固定 offline fixture 或真实搜索扩展样本来测。
- 2026-06-16 `v020_fix_verify` 观察：`schema_validation_report` 已为 0 invalid，SQLite `agent_query quality-flags` 返回空列表，短标题和空正文问题在真实 run 中得到验证；`search_relevance` shadow 有 5 个样本且 5/5 success，SearchExpansion 的 LLM query/relevance 也跑通。但内容质量仍为 61/`needs_review`，Xbox Wire 因 SSL EOF 三次失败，`source_dominance_audit` 显示游民星空占 77% 候选，`content_review.md`/`human_review_template.json` 未稳定生成，`editorial_judgment` 仍 1/5 success、4/5 fallback。详见 `docs/experience.md#EXP-2026-06-16-06-v020_fix_verify-真实验证与-Agent-工程化下一步`。
- 2026-06-17 `v020_ultracode_review` 观察：前 4 项方向正确，但 LLM shadow gate 曾与 prompt contract 错位，已修正并补回归测试。服务化现在可以前置为内部工作台，用来集中人工评分、通知、artifact 浏览和 LLM shadow 对比；工作台不做平台发布、登录或 LLM 事实改写。详见 `docs/experience.md#EXP-2026-06-17-01-v020_ultracode_review-审查与服务化工作台决策`。
- 0.2.0 进入服务化前的最低门槛：一次真实 run 能生成确定性主产物、SQLite mirror、agent query 可读结果、schema validation 关键 artifact 无 invalid、LLM shadow 至少在 query compression 和一个语义判断任务上各有正向/失败/边界样本。

PDF 参考架构：

- `智览AI项目组成参考.md` 已整理原 PDF 的技术栈、模块、接口和目录结构。可参考 `FastAPI`、`Nuxt 3 + Vue 3`、`Tailwind CSS`、`ECharts`、`Redis`、`LangGraph`、`LangChain` 的分层方式；短期不照搬 Elasticsearch/HDBSCAN/Celery/Nginx 全栈部署。

成功标准：

- 同一 URL、同一标题轻改、同源分页转载不会重复占据某个板块的 10 条最终 story 名额。
- 官方源和权威媒体的重复报道会合并为证据集合，而不是丢掉来源。
- 发布会/直播/直面会期间的连续资讯能形成事件时间线，重要新 detail 不会被误删。
- `content_review.md` 能显示某条 story 的 `cluster_id`、主报道、补充报道、重复报道数量和人工/LLM 待复核项。

### Phase 4.6：发售日期与游戏日历更新

目标：建立 `GameReleaseCalendar`，让系统能持续更新各游戏的发售日期、平台、地区和延期/改期记录，并把它作为新闻筛选、历史背景、发售提醒和“那年今日/本周发售”内容的结构化事实来源。

核心原则：

- 发售日期是事实型资料，不是社交热度。社交平台只能提示“玩家正在讨论延期/发售”，不能直接写入日历。
- 同一游戏可能有多平台、多地区、多版本日期，例如 Steam 抢先体验、PS5/Xbox/NS 实体版、DLC、豪华版提前游玩、中文区发行日，应分开记录。
- 日期精度必须显式标注：`exact_date`、`month_window`、`quarter_window`、`year_window`、`tbd`、`shadow_drop`、`released`。
- 任何日期变更都要保存 `release_date_change_event`，包含旧值、新值、来源、发现时间、置信度和原因标签，不能只覆盖最新字段。

数据产物规划：

- `game_release_records.json`：当前游戏日历快照。字段包括 `game_id`、`canonical_title`、`aliases`、`platforms`、`regions`、`release_dates`、`date_status`、`source_urls`、`confidence`、`last_checked_at`。
- `release_date_changes.json`：本轮检测到的新发售日、延期、提前发售、平台新增、地区新增、已发售确认等变化事件。
- `release_date_evidence.json`：官方页面、平台商店页、Steam app、Nintendo/PS/Xbox store、发行商公告、权威媒体报道等证据片段。
- `release_calendar_review.md`：人工核对入口，用于确认模糊日期、跨地区差异、同名游戏误合并和低置信度改期。

来源优先级：

1. 官方与平台商店：发行商/开发商官网、Steam、PlayStation Store、Xbox Store、Nintendo eShop、Epic、GOG。用于最高置信度日期。
2. 官方新闻与直播物料：press release、官方博客、YouTube/Bilibili 官方预告简介、发布会页面。用于确认新公布日期或窗口。
3. 权威媒体：IGN、GameSpot、PC Gamer、游民星空等。用于补充官方未结构化的日期，但需要来源交叉或人工/LLM核查。
4. 游戏数据库/API：IGDB、RAWG、Steam API 等可作为候选来源或批量补全工具；接入前要检查授权、字段质量和地区/平台粒度。
5. 社交平台：只作为“玩家正在讨论延期/发售/跳票”的热度和线索来源，不能作为最终日期事实。

更新流程：

```text
Candidate/Story/Game Alias
 -> GameIdentityResolver(规范名、别名、平台、系列)
 -> ReleaseDateCollector(官方/商店/媒体/API)
 -> ReleaseDateNormalizer(日期精度、地区、平台、版本)
 -> ReleaseDateComparator(旧记录 vs 新证据)
 -> ReleaseDateChangeClassifier(new_date/date_changed/delayed/advanced/platform_added/region_added/released_today)
 -> ReleaseCalendarReviewer(低置信度与冲突人工/LLM复核)
 -> GameReleaseCalendarStore(JSON -> SQLite/FTS -> RAG memory)
```

LLM/Agent 使用边界：

- `ReleaseDateAgent` 可以把“2026 年冬”“明年春季”“现已推出”“豪华版提前 3 天解锁”等自然语言归一化成结构化 JSON。
- LLM 不能凭空补日期，不能把未引用来源的媒体摘要当事实，不能合并同名不同游戏。
- 低置信度或冲突日期必须写入 `release_calendar_review.md`，由人工确认后再进入高置信度日历。

接入时机：

- 短期只对入选 story 和主题候选池 Top N 做增量更新，不全量爬所有游戏。
- 当发售日期记录积累稳定后，再支持“本周发售”“下月重点发售”“延期汇总”“某发布会公布的所有发售日”等内容板块。
- RAG-2 后把发售日变化与历史记忆结合，用于生成“首次公布于某年发布会、历经多次延期、终于定档”的背景句。

### Phase 5：排版成图

- 进入 Phase 5 前新增热度验证约束：`DiscussionProbe` 不再只面向固定中文平台，而是通过 `RegionalHeatProbe` 按来源语言/地区选择验证平台。中文来源优先 Bilibili、微博、贴吧、小黑盒；英文来源优先 Reddit、YouTube、Steam、X；日文来源预留 X Japan、YouTube、NicoNico、5ch。这个层只证明“是否正在被讨论”，不证明事实本身。
- 地区热度必须先通过游戏相关性与可发布门：社会新闻、娱乐八卦、泛科技、折扣、攻略、普通补充上下文即使在社交平台有热度，也只能进入人工/LLM 参考池，不能被规则 verifier 自动标为可发布 story。
- 证据链约束同步收紧：候选没有抓到自己的正文时，可以把相似 chunk 放进 context pack 给 LLM/人工参考，但不能作为确定性 claim evidence 写入 `source_urls` 或 `evidence_chunk_ids`。后续跨语言翻译、中文替代和 story cluster 合并都必须建立在这个边界上，避免把不同英文来源的无关文章误合成一个 story。
- 实现 HTML/CSS 模板。
- 使用 Playwright 渲染 PNG。
- 每条图都有可追溯素材来源。
- 当前状态：暂缓。等 Phase 4.5 能稳定判断“哪些内容值得继续加工”后，再把 `stories.json`、`platform_posts.json`、素材状态和平台画布尺寸合并成真正的 `layout_manifest.json` 内容块。

### Phase 6：内容运营

- 先半自动发布。
- 再按平台能力接自动发布。

### Phase 6.5：CrewAI 创作侧车

目标：在事实链路完成后，引入更自由的创作讨论，但不破坏主流程可测试性和证据可追踪性。

可选角色：

- `CreativePitchCrew`：输入已验证 stories/context packs，输出标题角度、社媒开场、梗图角度、争议角度。
- `LayoutCritiqueCrew`：输入 layout manifest 和素材状态，输出微博长图、小红书轮播、Bilibili 动态图的版面修改建议。
- `CommunityToneCrew`：输入补充池、社区热度摘要、平台风格规则，输出运营口吻和评论区互动建议。

输入边界：

- 只读取 `stories.json`、`context_packs.json`、`claims.json`、`assets.json`、`layout_manifest.json`、`supplemental_candidates.json`。
- 不直接访问网络，不新增事实，不改 claim 状态，不改证据。

输出边界：

- 只写 `creative_suggestions.json`。
- 每条建议必须引用对应 story/candidate id。
- 后续由 LangGraph 的 `OpsReviewer` 或人工审核决定是否采用。

接入顺序：

1. 先完成主流程的 `ClaimExtractor`、`EvidenceVerifier`、`MarkdownEditor`。
2. 再实现一个离线 `CreativePitchCrew` 原型，只读取固定 artifact。
3. 验证不会增加事实幻觉风险后，再接 `LayoutCritiqueCrew`。

### Phase 7：连接过去与现在

- 寻找和当前资讯有关联的往日资讯。
- 找寻关系，寻找类似于“当前资讯是往日资讯的续集”、“当前资讯是首次达成某种状态或者成就，如首次发布、首次被评论、首次被转发、首次成为第一个相隔XX年后才正式发布等”等的关系。
- 类似 NBA 新闻写法：生成“自 A/YY 年以后，B 是第一个做到 XXX 的游戏/厂商/玩家/平台”这类背景句。
- 历史纪录类内容必须由 `HistoricalContextMiner` 通过历史 evidence store 或权威外部来源检索得到。
- 输出时分成三类：
  - `confirmed_record`：证据充分，可写入正文。
  - `record_candidate`：证据不足，只能作为编辑提示。
  - `analogy`：只是类比或叙事辅助，不能写成事实纪录。
- 该阶段优先服务于“增强内容味道”，不应牺牲 48 小时主新闻的准确性和时效性。

## 2026-05-14 SearchCollector 修改方案补充

本轮先采用“A + 一点 B”：先做最小 HTTP fetcher，再接 4 个权威媒体源；在权威媒体闭环可运行前，不接 X、贴吧、小黑盒、Bilibili、微博等社区源。

### 搜索模块是否够用

当前搜索模块如果只依赖一个通用搜索引擎会不够用，原因是：

- 游戏资讯站点数量有限，固定权威源优先级高于全网泛搜。
- 通用搜索结果经常给旧闻、聚合页、无时间戳页面，容易复现初次 demo 的时间范围失控。
- 资讯热度和事实可信度不是同一件事：权威媒体源适合建立事实候选，社区源后续再用于热度、梗图、玩家截图和传播强度。

修改为分层 SearchCollector：

```text
SourcePlanner
 -> SourcePlan(固定源、collector 类型、入口 URL、优先级)
 -> HttpFetcher(最小 HTTP 文本抓取)
 -> CollectorRegistry(RSS / listing page / future browser/API)
 -> CandidateNormalizer(SearchCandidate)
 -> SourceRelevanceGate(来源 URL 范围、游戏相关性、明显噪声过滤)
 -> MemoryFreshnessGate(旧闻复读 vs 当天更新)
 -> TimeWindowFilter(48h hard gate)
 -> CandidateTypeGate(news/rumor/platform_price/hardware_platform vs guide/deal/general_tech/meme_gallery)
 -> HeatScorer
```

### Phase 2A：权威媒体最小闭环

首批只接：

- IGN：`media_rss`
- PC Gamer：`media_rss`
- GameSpot：`media_rss`
- 游民星空：`media_listing`，先解析资讯列表页；如果后续发现稳定 RSS/API，再替换 collector。

输出要求：

- `raw_sources.jsonl`：每个源的抓取状态、HTTP 状态码、content-type、错误信息。
- `candidates.json`：通过时间窗和记忆过滤后的候选。
- `supplemental_candidates.json`：通过基础过滤但不进入主新闻的候选，例如攻略、折扣、泛科技、轻图集，后续可用于填充或人工挑选。
- `rejected_candidates.json`：缺时间、超出时间窗、旧闻复读、来源范围不匹配、明显非游戏内容等被拒条目。
- `collector_errors.json`：联网失败、RSS/XML 解析失败、站点结构不匹配等错误。

### 2026-05-15 联网验证结论与修复

用户本地生成的 `outputs/langgraph/live_test/` 显示 4 个权威源均可联网成功，`collector_errors.json` 为空；但候选质量暴露出两个必须前置修复的问题：

- IGN 的通用 RSS 会混入影视、购物和硬件折扣等非游戏内容，不能直接进入候选池。
- 游民星空列表页会抓到 `hardware`、`handbook` 等非资讯 URL，需要先收紧 URL 范围。

已补入第一版 `SourceRelevanceGate`：

- 来源可在 `collector_config` 中声明 `allowed_url_patterns`、`excluded_url_patterns`、`required_any_keywords`、`excluded_keywords`。
- 不再把 query seed 例如 `games` 当作游戏相关性的证据，避免所有候选天然通过关键词门。
- 被拒候选统一标为 `irrelevant_topic`，并在 `relevance_reasons` 中记录 `url_not_allowed`、`missing_required_keyword`、`excluded_keyword:*` 等细分原因。
- `HttpFetcher` 增加 header/meta/UTF-8/GB18030 顺序解码，降低中文页面乱码风险。

2026-05-15 继续补入 `CandidateTypeGate`：

- 主新闻保留 `news`、`rumor`、`platform_price`、`hardware_platform`。
- 补充池接收 `guide`、`deal`、`general_tech`、`meme_gallery`。
- 后续全文抓取和 RAG 默认只处理主新闻 Top N；补充池只作为填充、人工挑选或低成本摘要来源。
- 这一步不调用 LLM，先用透明规则把 token 花费挡在 RAG 之前。

在无法再次联网的沙箱中，用用户已生成的 `live_test/candidates.json` 离线重放验证：原 200 条候选过滤后剩 173 条；IGN 从 20 条降到 7 条；游民星空从 100 条降到 86 条；新增拒绝 27 条，均为 `irrelevant_topic`。下一次用户在 IDE 中运行 `D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py` 后，应重点检查这 4 个源的 `source_health.json` 是否仍为 healthy，以及 IGN 是否不再出现明显影视/购物内容。

### 48h 与记忆关联

48h 不应该只看媒体发布时间，还要和“这件事是不是早就出现过”关联：

- `new_story`：记忆里没有相关事件，按正常候选处理。
- `known_recent_story`：记忆里有，但首次出现仍在 48h 内，保留。
- `late_repost`：首次出现早于 48h，当前候选只是晚发复述，默认拒绝，避免把旧闻当新热度。
- `follow_up_update`：首次出现早于 48h，但当前候选包含当天新变化、新地区价格、新官方回应、新数据或新证据，保留并标注“后续更新”。

第一版实现只做轻量钩子：候选可带 `memory_key`、`is_current_update`、`related_story_id`；后续接 RAG/evidence store 后，再由 DedupClusterer 和 HistoricalContextMiner 自动生成这些字段。

### 后续搜索增强顺序

1. 先稳定 4 个权威媒体源的 RSS/listing 采集。
2. 再加入官方源 RSS/API：Xbox Wire、PlayStation Blog、Nintendo、Steam News。
3. 再接结构化搜索 API：Brave/Tavily/SerpAPI/Bing 之一，用于补充“固定源没覆盖但权威媒体转发过”的新闻。
4. 最后接社区热度源：Bilibili、微博、贴吧、小黑盒等，并与权威媒体事实候选分开评分。

### Phase 8：权威流言日常化

- 将权威媒体/权威自媒体/舅舅党爆料纳入日常采集类型。
- 为爆料源建立 `rumor_source_profile`：历史准确率、领域、常见平台、被权威媒体引用次数、风险备注。
- 流言进入主流程时必须保留原始措辞，例如“透露”“暗示”“据称”“可能”，不得自动改写成确定事实。
- 当流言被官方确认或否认时，系统要能把旧流言和新事实关联起来，形成”流言 -> 官宣/辟谣”的后续链路。

### Phase 9：内部工作台 (SVC-001~004) — 2026-06-17 已落地 ✅

SVC-001 FastAPI Run/Artifact API、SVC-002 Nuxt3 Internal Workbench、SVC-003 Human Review Capture、SVC-004 Read-only Safety Guard 已全部实现并通过 47 个回归测试。

关键决策：先做内部工作台再深入 Agent/RAG 行为。理由：
- 确定性管道已产出足够 review 的工件，但人工 review 仍然太依赖文件系统。
- LLM shadow 只有在用户能对比确定性结果并评分差异时才有用。
- SQL/RAG/Agent 工作需要标签和失败案例；工作台是收集这些的最快路径。
- Service API 为未来 Agent 创建稳定边界：Agent 调用白名单查询/评审端点，而非读取任意文件或写任意 SQL。

实现结构：
- `LangGraph/service/`：FastAPI 独立 deployable，import `persistence/agent_query.py`，9 个只读端点 + 人工评审 POST/GET
- `LangGraph/workbench/`：Nuxt3 SPA，纯展示层，通过 REST API 调用 FastAPI
- `docs/FastAPI/api-contract.md`：API 合约文档
- `docs/Vue/workbench-guide.md`：前端工作台指南
- 安全 guard 阻挡：路径穿越、任意 SQL、发布动作、非 GET/POST 方法、非 human-reviews 的 POST

测试：47/47 通过，4 个 harness 合约全部标记 `implemented`。

对应 issue：SVC-001, SVC-002, SVC-003, SVC-004 已关闭。

