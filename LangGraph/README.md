# Games News Agent - LangGraph Skeleton

这是多智能体游戏资讯智能体的新核心骨架。当前版本已经搭好 LangGraph 状态机、数据结构、来源配置、离线 harness 和最小 live collector。当前 dry-run 会优先读取 `harness/sample_candidates.json` 做离线回放，再应用 48 小时时间窗口、记忆过滤、来源相关性过滤和热度排序。

目标流程（2026-06-16 当前实际 graph）：

```text
plan_sources
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

安装：

```powershell
cd LangGraph
pip install -e .
```

空跑：

```powershell
games-news-agent --dry-run --lookback-hours 48 --topic "games"
```

也可以直接：

```powershell
python -m games_news_agent.run --dry-run
```

本地 IDE 联网验证，不需要先安装包：

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py
```

如需跨多次真实联网运行复用候选记忆库，用同一个 `--memory-path`：

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 48 --topic games --document-fetch-limit 20 --output-dir outputs\langgraph\memory_live --memory-path outputs\langgraph\memory\candidate_memory.json
```

候选记忆库默认写入 `outputs/langgraph/memory/candidate_memory.json`，记录已通过基础过滤的 main/supplemental 候选，用于后续识别旧闻复读、同一事件的晚发转载和带当天变化的 follow-up。

`--theme-candidate-pool-limit` 控制 `theme_candidate_pool.json` 中保留的平衡主题候选数量，默认 100；`--document-fetch-limit` 控制每个主题板块本轮最多抓取多少篇正文。也就是说，`--document-fetch-limit 20` 代表索尼、任天堂、微软、PC、补充板块各最多 20 条正文，不再把主题候选池截断成全局 20 条。

这个入口默认运行 live collector，输出到项目根目录的 `outputs/langgraph/live_test/`。重点看：

- `source_health.json`：每个已启用 live 源的简短状态分类。
- `source_theme_counts.json`：每个来源在索尼、任天堂、微软、PC、补充板块中各产出多少候选；用于判断缺口到底在 IGN/GameSpot/游民星空等哪个源、哪个主题。
- `collector_errors.json`：抓取或解析错误。
- `collector_diagnostics.json`：每个来源/入口的检索诊断，包含链接数、候选数、缺时间数、重复 URL、详情页时间回填数和解析告警数。
- `source_navigation_requests.json`：给 LLM SourceNavigator 的请求包，只包含实际观测到的 URL，用于辅助判断哪些入口更值得后续配置或抓取。
- `source_navigation_results.json`：启用 `--run-llm-source-navigator` 后的 SourceNavigator 结果；默认空列表。
- `source_recovery_plan.json`：采集层 Agent 诊断计划。它只根据已有 artifact 推荐下一步工具/配置检查，例如增量分页、时间回填、主题缺口、过滤规则或浏览器探针，不直接产出新闻事实。
- `search_expansion_requests.json`：SearchExpansion v0 的主题查询包，用于扩展索尼、任天堂、微软、PC 和补充板块的候选线索。
- `search_expansion_observations.json`：启用 `--run-search-expansion` 后的公开搜索页观测结果。
- `search_expansion_candidates.json`：从有效搜索观测中转出的 supplemental 候选线索。
- `discussion_probe_requests.json`：DiscussionProbe v0 的低频/人工搜索请求包，按候选 `source_language` / `heat_region` 选择 Bilibili、微博、贴吧、小黑盒、Reddit、YouTube、Steam、X、NicoNico 等地区平台入口。
- `discussion_probe_report.json`：基于候选和已抓取正文证据生成的讨论证据报告，只证明“可能在讨论”，不证明事实本身。
- `candidates.json`：通过 48 小时窗口、记忆过滤、来源相关性过滤的候选。
- `supplemental_candidates.json`：已通过基础过滤、但更适合作为补充素材的攻略、折扣、泛科技、轻图集等候选。
- `rejected_candidates.json`：因缺时间、超窗口、旧闻复读、明显非游戏内容或来源 URL 不匹配等被拒绝的候选。
- `candidate_memory.json`：默认位于 `outputs/langgraph/memory/`，跨运行记录已见过的候选，用于后续识别复读和 follow-up。
- `documents.json`：对主候选 Top N 抓取或 dry-run 合成的正文文档。
- `evidence_chunks.json`：从正文文档切出的轻量证据块。
- `context_packs.json`：给后续 LLM verifier/editor 使用的紧凑上下文包；`evidence_scope=candidate_url` 才会作为确定性 claim evidence，`retrieved_context` 只作为参考上下文。
- `claims.json`：从 context pack 生成的候选级 claim，当前为确定性脚手架，后续替换为 LLM 拆 claim。
- `claim_verifications.json`：规则版 EvidenceVerifier 输出，当前只做证据重叠检查，后续替换为 LLM 语义核查。
- `llm_verification_requests.json`：给后续 LLM verifier 的请求包；当前只生成请求，不直接调用模型。
- `llm_verification_results.json`：启用 `--run-llm-verifier` 后的 LLM 原始核查结果。
- `stories.json`：从已验证/可信 claim 聚合出的 story 列表，包含 story score、状态、编辑标签和来源。
- `source_selection_diagnostics.json`：统计每个来源从 raw、main/supplemental、theme pool、正文抓取、story candidate 到 final story 的流失情况，并包含 `document_errors`、`evidence_scope_counts`、`missing_field_counts`，用于解释 IGN/英文来源为什么入池或入选较少，以及正文证据是否降级为参考上下文。
- `story_localization_requests.json`：英文 story 的本地化请求包。它只准备“中文翻译 + 在已观测中文候选中寻找同事件替代”的 LLM/人工审核输入，不直接改变事实状态。
- `editorial_judgment_requests.json`：给未来 `EditorialJudgmentAgent` 的高风险/模糊候选判断请求包。它只判断游戏相关性、热度有效性和可发布建议，不新增事实、不改证据。
- `platform_posts.json`：把 story 转成微博、小红书、Bilibili 的平台文案草稿，并把内部流言状态折叠成外部标签。
- `content_quality_report.json`：Phase 4.5 内容质量报告，评估来源健康、热度信号、证据覆盖、流言核查、来源集中度和素材缺失，并为每个环节生成 0-100 分。
- `content_review.md`：给人工评价真实联网内容的评审包，包含机器评分、入选 story、证据摘录、文案预览和人工评分表。
- `human_review_template.json`：人工评价结构化模板，用来记录你希望靠近的风格和高分方向。

注意：项目根目录的 `main.py` 是旧 CrewAI demo 入口。LangGraph 联网验证请使用 `LangGraph/main.py`。

输出默认写入：

- `outputs/langgraph/latest/briefing.md`
- `outputs/langgraph/latest/raw_sources.jsonl`
- `outputs/langgraph/latest/source_theme_counts.json`
- `outputs/langgraph/latest/collector_errors.json`
- `outputs/langgraph/latest/collector_diagnostics.json`
- `outputs/langgraph/latest/source_navigation_requests.json`
- `outputs/langgraph/latest/source_navigation_results.json`
- `outputs/langgraph/latest/source_recovery_plan.json`
- `outputs/langgraph/latest/search_expansion_requests.json`
- `outputs/langgraph/latest/search_expansion_observations.json`
- `outputs/langgraph/latest/search_expansion_candidates.json`
- `outputs/langgraph/latest/discussion_probe_requests.json`
- `outputs/langgraph/latest/discussion_probe_observations.json`
- `outputs/langgraph/latest/discussion_probe_report.json`
- `outputs/langgraph/latest/candidates.json`
- `outputs/langgraph/latest/supplemental_candidates.json`
- `outputs/langgraph/latest/rejected_candidates.json`
- `outputs/langgraph/latest/theme_candidate_pool.json`
- `outputs/langgraph/latest/documents.json`
- `outputs/langgraph/latest/evidence_chunks.json`
- `outputs/langgraph/latest/context_packs.json`
- `outputs/langgraph/latest/story_clusters.json`
- `outputs/langgraph/latest/claims.json`
- `outputs/langgraph/latest/claim_verifications.json`
- `outputs/langgraph/latest/stories.json`
- `outputs/langgraph/latest/source_selection_diagnostics.json`
- `outputs/langgraph/latest/story_localization_requests.json`
- `outputs/langgraph/latest/editorial_judgment_requests.json`
- `outputs/langgraph/latest/assets.json`
- `outputs/langgraph/latest/platform_posts.json`
- `outputs/langgraph/latest/content_quality_report.json`
- `outputs/langgraph/latest/content_review.md`
- `outputs/langgraph/latest/human_review_template.json`
- `outputs/langgraph/latest/material_bundle.json`
- `outputs/langgraph/latest/llm_verification_requests.json`
- `outputs/langgraph/latest/llm_verification_results.json`
- `outputs/langgraph/latest/layout_manifest.json`
- `outputs/langgraph/latest/render_queue.json`

运行追踪（`run_trace` 节点写入 `artifacts_by_stage/run_trace/`）：
- `run_manifest.json`：运行清单（run_id、开始/结束时间、节点摘要）
- `run_events.jsonl`：node_started/finished/failed、fetch attempts、artifact writes 等事件
- `user_notifications.json`：面向用户的通知（warning、error、info）

社交热度与诊断：
- `social_heat_observations.json`：社交热度观测（平台、结果数、讨论提示）
- `social_heat_relevance_checks.json`：社交相关性检查（on_topic/off_topic/same_platform_only）
- `semantic_relevance_requests.json` / `semantic_relevance_results.json`：语义相关性复核请求与结果
- `source_dominance_audit.json`：单源支配度审计

Story 与主题：
- `story_candidates.json`：进入主题精排前的全量 story 候选
- `theme_sections.json`：五个主题板块的候选数、入池数、入选数
- `theme_candidate_pool.json`：正文抓取前的平衡主题候选池
- `theme_story_ranking_diagnostics.json`：每板块 Top story 的排序理由与加权项

Phase 4.5 物料包：
- `assets.json`：从已抓取正文的 `image_urls` 里提取文章图、OG image 等可用素材 URL，保留原文 URL、来源、标题和文档索引。
- `material_bundle.json`：把 story、证据摘录、平台文案、可用素材 URL、缺图标记和人工评分字段放在一起。它不下载图片，也不调用 LLM 生成图片；读取不到素材时标为 `manual_fill_required`，给后续排版留空或人工补图。

新增或修改新闻源：

所有来源都写在 [config/sources.yaml](D:/PythonProjects/Games_News_Crew/LangGraph/config/sources.yaml)。

常用字段：

- `id`：稳定唯一 ID，例如 `ign`、`xbox_wire`。
- `name`：显示名，会出现在 `source_health.json` 和 `source_theme_counts.json`。
- `kind`：`official`、`media`、`community`、`search`。
- `collector`：当前可真实联网的类型是 `media_rss`、`media_listing`、`media_incremental_listing` 和 `media_jsonp_paged_listing`；`*_stub` 只是计划占位，不会进入 live collector。
- `feed_url` / `feed_urls`：RSS 源，一个或多个。
- `page_url` / `page_urls`：列表页，一个或多个。
- `feed_entries` / `page_entries`：带元数据的入口列表，每项可写 `url`、`label`、`theme_section`、`tags`；适合 IGN 这类同站多主题入口。
- `collector_config.allowed_url_patterns`：限制列表页只收哪些 URL。
- `collector_config.excluded_url_patterns`：排除哪些 URL。
- `collector_config.article_url_patterns`：当普通 `<li>` 列表解析不到候选时，允许 `article_link_fallback` 抽取的文章 URL，例如 IGN 的 `^https://www\.ign\.com/articles/`。
- `collector_config.next_url_patterns`：用于 `media_incremental_listing`，从页面里提取“Load More/下一页”链接；默认可识别 `endIndex=N` 这类链接。
- `collector_config.pagination_url` / `pagination_entries`：用于 `media_jsonp_paged_listing`，适合“点击栏目/翻页后由 JSON 或 JSONP 返回 HTML 列表片段”的站点。入口按 `node_id`、`label`、可选 `theme_section` 配置，不把 collector 命名绑定到具体网站。
- `collector_config.max_pages_per_entry` / `stale_page_stop_count`：控制动态列表最多翻几页，以及连续遇到已经早于 lookback 窗口的页面后停止。
- `collector_config.required_any_keywords`：必须命中任一关键词。
- `collector_config.excluded_keywords`：命中即拒绝的关键词。
- `collector_config.section_node_theme_map`：把列表页内部 tab 节点映射到主题板块，例如游民星空 `data-nodeid=21160` 对应 `nintendo`。
- `tags`：来源标签，会进入候选 metadata。

最小 RSS 示例：

```yaml
  - id: example_media
    name: Example Media
    kind: media
    url: https://example.com/
    feed_urls:
      - https://example.com/rss/news.xml
      - https://example.com/rss/playstation.xml
    region: global
    priority: 75
    collector: media_rss
    tags: [media, global]
```

最小列表页示例：

```yaml
  - id: example_cn
    name: 示例中文站
    kind: media
    url: https://example.cn/
    page_urls:
      - https://example.cn/news/
      - https://example.cn/xbox/
    region: cn
    priority: 75
    collector: media_listing
    collector_config:
      allowed_url_patterns:
        - '^https://example\.cn/news/'
    tags: [media, cn]
```

Collector：

- `fetching.py`：最小 HTTP 文本抓取器，支持 header/meta/UTF-8/GB18030 顺序解码。
- `collectors/rss.py`：解析已经获取到的 RSS/XML 文本，输出统一 `SearchCandidate`。
- `collectors/listing.py`：解析媒体列表页和动态接口返回的 HTML 列表片段；普通 `<li>`、`data-nodeid` tab 和 IGN 文章链接 fallback 都统一产出 `SearchCandidate`。
- `collectors/registry.py`：根据 source 配置调度 RSS、静态列表页、Load More 增量列表和 JSONP 分页列表；JSONP 分页用于“点击栏目/翻页才加载更多”的页面，Load More 增量列表用于 IGN 这类 `endIndex` 链接。后续可继续扩展 NextData/browser/LLM-assisted 入口。
- `collectors/web.py`：解析已经获取到的 HTML 文本，输出统一 `SourceDocument`。
- `candidate_types.py`：把候选分成主新闻和补充池，避免攻略、折扣、泛科技内容污染后续 RAG。
- `deduplication.py`：在 claim extraction 前标注 story cluster，先解决 FF6 AI 重制这类同一事件多条文章重复占位的问题。
- `document_fetching.py`：抓取主候选 Top N 的文章正文；dry-run 下用候选标题和摘要合成文档。
- `search_expansion.py`：SearchExpansion v0，按主题缺口生成短查询，低频观测公开搜索页，并把相关结果转成 supplemental 候选线索。
- `regional_heat.py`：按候选语言/来源/URL 推断热度验证地区，并生成对应社区、视频或游戏平台搜索入口；只生成接口数据，不确认事实。
- `discussion_probe.py`：DiscussionProbe v0，生成低频/人工搜索入口，并从候选与正文证据中提取讨论平台、讨论语言和多平台复现信号。
- `discussion_probe_provider.py`：DiscussionProbeProvider v1，可选低频抓取公开搜索页，只记录搜索结果标题、片段、状态码、结果提示和互动提示，不确认事实。
- `evidence_store.py` / `retrieval.py` / `context_packs.py`：轻量 RAG 骨架，先用文本切块和关键词检索。
- `claim_extraction.py`：先生成候选级 claim，保留 source URLs、evidence chunk ids、missing fields 和 claim type；非发布型补充内容会进入 `supplemental_context`，不走自动发布事实链。
- `evidence_verification.py`：先用确定性规则把 claim 标成 `likely`、`rumor` 或 `reject`，给后续 LLM verifier 固定输出合同；`supplemental_context` 默认 reject，只能作为人工/LLM 参考。
- `llm_verifier.py`：准备 LLM 核查请求、校验 LLM JSON 返回、把 LLM 结果合并回 claim verifications。
- `llm_provider.py`：OpenAI-compatible 调用层，优先读取 `.env` 中的 DeepSeek 配置。
- `prompts/evidence_verifier.md`：LLM verifier 的提示词模板和 JSON 输出格式。
- `prompts/claim_extractor.md`：LLM claim 拆解 prompt。
- `prompts/markdown_editor.md` / `prompts/platform_writer.md` / `prompts/layout_designer.md`：简报、文案、排版 prompt。
- `prompts/historical_context_miner.md`：历史背景挖掘 prompt。
- `prompts/search_query_compressor.md` / `prompts/search_result_relevance.md`：SearchExpansion 用 query 压缩和搜索结果相关性分类 prompt。
- `prompts/prompt_registry.json`：prompt 统一注册表（id、版本、输入输出、fallback）。
- `markdown_editor.py`：把候选、claim verification、证据和 LLM rationale 生成可审核 Markdown 简报。
- `story_ranking.py`：把可发布或待审的 claim 聚合成 story，并计算 story score。
- `source_selection_diagnostics.py`：解释来源和语言在各阶段的流失点，避免只凭最终 Top 10 判断某个源是否抓取失败。
- `story_localization.py`：为英文 story 生成中文翻译/中文替代请求，并校验后续 LLM 返回不能引用未观测 URL。
- `editorial_judgment.py`：为未来多智能体中的 `EditorialJudgmentAgent` 生成判断请求并解析 JSON 结果。它只做游戏相关性、热度有效性和可发布建议，不验证事实、不新增来源。
- `platform_writer.py`：生成平台文案草稿，外部标签保持简单：例如 `[流言][可信爆料]`、`[流言][待验证]`、`[流言][未验证]`。
- `content_quality.py`：在进入排版前输出内容质量门，先评价内容本身是否值得继续加工；当前评分环节包括来源采集、候选过滤、正文证据、Claim 核查、Story 选择和平台文案。
- `content_review.py`：生成面向人工评价的 review pack，让机器分数和真实联网内容并排出现，方便你决定高分风格。
- `materials.py`：生成 `assets.json` 和 `material_bundle.json`，把可用素材、缺图标记、证据摘录、平台草稿和人工评审入口合并成 Phase 4.5 的真实物料包。

以下模块为 2026-06 新增，尚未在 README 中逐项描述；详细说明见 `docs/roadmap.md` 相关章节和 `docs/issues.md`：

- `event_timeline.py`：事件时间线构建，区分 `duplicate_report`、`same_event_followup` 等。
- `source_recovery.py` / `source_recovery_agent.py` / `source_recovery_suggestion.py`：采集恢复诊断与 Agent。
- `social_heat.py` / `social_heat_relevance.py`：社交热度观测与相关性门。
- `source_dominance.py` / `source_health.py` / `source_metrics.py` / `source_navigation.py`：来源健康、支配度审计与导航诊断。
- `selection_backfill.py` / `selection_diagnostics.py`：板块均衡回填与入选诊断。
- `search_intelligence.py` / `search_expansion_llm.py`：搜索智能化（query 压缩、相关性分类、LLM 扩展）。
- `story_cluster_review_agent.py`：story cluster 复核 Agent。
- `llm_shadow.py` / `langchain_adapter.py`：LLM shadow mode 基础设施与 LangChain 适配。
- `prompt_registry.py`：prompt 注册表 loader 与校验。
- `run_trace.py`：运行追踪（`run_manifest.json`、`run_events.jsonl`、`user_notifications.json`）。
- `artifact_manifest.py` / `artifact_schema_registry.py`：分阶段 artifact 清单与 schema 注册。
- `site_parser_contract.py`：站点解析器契约。
- `user_notification_contract.py`：用户通知契约。
- `agent_contracts.py`：Agent 决策、评分、恢复计划等数据契约。
- `persistence/`：`event_store.py`、`sqlite_mirror.py`、`historical_import.py`（SQL 事件库与镜像）。

已启用的 live 源：Nintendo Official、PlayStation Blog、Xbox Wire、IGN、GameSpot、PC Gamer、游民星空。御三方官方源用于补齐索尼/任天堂/微软主题的基础覆盖和权威证据，不直接代表高热度；热点仍要看媒体转载、评论、弹幕、转发和多平台讨论信号。来源规则写在 `config/sources.yaml` 的 `collector_config` 中，当前用于过滤官方源和 IGN 的影视/购物噪声，以及限制游民星空只进入资讯 URL。

启用 LLM verifier：

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --dry-run --document-fetch-limit 3 --run-llm-verifier --llm-verification-limit 1
```

默认不启用真实 LLM 调用；只有传入 `--run-llm-verifier` 才会读取 `.env` 并请求模型。

启用 LLM SourceNavigator：

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 48 --topic games --document-fetch-limit 20 --run-llm-source-navigator --llm-source-navigation-limit 3
```

SourceNavigator 只会从本轮已经观测到的 URL 中推荐入口，不允许发明 URL；它用于辅助改进 source 配置，不直接产生事实结论。
当设置了较小的 `--llm-source-navigation-limit` 时，请求会优先发送给诊断痛点更高的来源，例如缺时间、重复 URL、零入选或大量 `irrelevant_topic` 的来源。
live 模式下 `search_candidates` 会在节点内部打印 source start/done 和详情页时间回填进度；如果这里停留较久，通常是在顺序抓取 RSS/listing 或低限额详情页回填。

启用 SearchExpansion：

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 48 --topic games --theme-candidate-pool-limit 100 --document-fetch-limit 20 --run-search-expansion --search-expansion-limit 8 --search-expansion-platform-limit 2
```

SearchExpansion 默认关闭。启用后只扩充 supplemental 候选线索，不直接确认事实；后续仍需正文抓取、DiscussionProbe 和 claim verification。

DiscussionProbe v0 默认启用，但不会抓取社交平台；它只生成可审计搜索入口，并使用已抓取正文中的讨论信号提升候选的 `discussion_profile`。可用 `--discussion-probe-limit` 控制最多处理多少个主题候选：

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 48 --topic games --document-fetch-limit 20 --discussion-probe-limit 20
```

DiscussionProbeProvider v1 默认关闭。启用后会按候选生成的公开搜索入口做低频观测，并写出 `discussion_probe_observations.json`；它只保存 `ok/blocked/error/skipped_manual`、`result_count`、`discussion_hint_count`、`top_results` 和 `evidence_texts`，不会登录平台，也不会把搜索结果改写成事实：

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 48 --topic games --document-fetch-limit 20 --discussion-probe-limit 5 --run-discussion-probe-provider --discussion-probe-provider-platform-limit 2
```
