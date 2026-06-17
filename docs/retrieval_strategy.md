# 游戏资讯检索方式诊断与进入 RAG 的标准

本文记录检索侧经验，避免把“网站入口问题”“时间戳提取问题”“热点发现问题”和“RAG 证据问题”混在一起。

## 当前结论

RAG 不能凭空发现热点。它适合在候选已经被找到后，做正文证据检索、claim 支撑、旧闻/后续更新对比和历史背景补充。  
如果 `theme_candidate_pool.json` 数量不足、主题偏科、时间戳缺失严重，优先修检索侧，而不是先接向量库。

但检索侧也不必等到“每个网站完美”。当失败原因可以被分类，且候选池能稳定产出可验证输入时，就可以进入 RAG 设计。

## 网站问题分类

### 1. 入口太宽

表现：

- 通用 RSS 或首页 feed 混入影视、购物、硬件折扣、泛娱乐。
- IGN、GameSpot、PC Gamer 这类权威站有候选，但主题分布不理想。
- `supplemental_candidates.json` 很多，主候选较少。

判断：

- 这不是 RAG 问题，而是 source entry 问题。
- 应优先寻找站内游戏新闻、PlayStation、Xbox、Nintendo、PC、review、rumor 等主题 feed/listing。
- 如果站点没有稳定主题入口，再用规则过滤和后续 DiscussionProbe 补强。

### 2. 时间戳缺失

以游民星空为例，`official_sources_live/source_theme_counts.json` 显示 raw 很多，但 `missing_time` 很高。可能原因：

- 列表页里包含大量历史链接、推荐链接、导航链接或专题链接，这些链接附近没有发布时间。
- 列表页只显示部分条目的时间，更多时间需要进入详情页抽取。
- HTML 结构里时间字段不是固定位置，当前 listing parser 只识别到一部分。
- 服务端返回的页面可能是静态降级版本、移动端/桌面端结构不同，或部分内容由 JS 延迟加载。
- 如果站点对非浏览器请求做降级，可能出现正文/时间戳被截断、空壳 HTML、推荐区重复等问题。

处理顺序：

1. 保存 raw HTML 采样，确认是否真的存在时间戳。
2. 统计列表页链接数、候选数、missing_time 数、重复 URL 数。
3. 对缺时间但 URL 看起来有效的条目做低限额详情页补时间。
4. 仍缺时间的条目进入 rejected 或 manual review，不进入主候选。
5. 如果详情页也缺时间，再考虑 browser/open-claw 类低频抓取，而不是扩大普通 HTTP 抓取。

### 3. 服务端截断或降级

风险信号：

- HTTP 200 但 HTML 很短。
- content-type 正常，但页面标题/正文像验证页、错误页、空壳页。
- raw links 数量异常少或异常多。
- 同一请求多次返回结构不同。
- 列表页可抓到链接，但抓不到发布时间、摘要、正文。

需要持久化的诊断字段：

- `raw_html_bytes`
- `content_type`
- `status_code`
- `redirect_url`
- `link_count`
- `candidate_count`
- `missing_time_count`
- `duplicate_url_count`
- `detail_time_backfill_count`
- `parse_warning_count`

这些字段能帮助判断是 parser 不够，还是网站服务端返回本身不适合普通 HTTP collector。

### 4. 平台及时性不足

权威媒体通常适合确认事实，不一定最先反映热点。  
X、微博、Bilibili、贴吧、小黑盒等平台更接近热点源，但它们不一定适合高频爬取。

建议定位：

- 权威媒体/官方源：提供事实候选和证据。
- 社区/社媒源：提供讨论热度、梗图、玩家截图、传播速度。
- 社区入口优先做低频、类人工、可审计 probe，而不是大规模爬虫。
- 对每条候选生成 2-4 个短查询，检查是否在多个平台出现讨论证据。

## 搜索方式可以算“过关”的条件

不是必须每轮 100 条，也不是必须每个网站都 healthy。达到以下条件，就可以认为检索方式足够进入 RAG 设计：

- `collector_errors.json` 中的错误都能分类：blocked、parse_warning、missing_time、site_entry_too_broad、detail_fetch_failed。
- 主要来源中至少 4 个能稳定产出候选，且不是全部来自同一站。
- `theme_candidate_pool.json` 总池稳定达到 60 条以上，或能明确说明不足板块由 `needs_fill` 填充。
- 索尼、任天堂、微软、PC 四个核心板块中，至少 3 个板块能稳定达到 8-10 条候选。
- 候选必须有 `title`、`url`、`source_id`、`published_at/observed_at` 中至少一个可靠时间字段。
- rejected 中 `unknown` 或无法解释的比例很低，绝大多数被拒理由能落到 `missing_time`、`outside_time_window`、`irrelevant_topic`、`late_repost` 等明确类别。
- `source_theme_counts.json` 能解释每个来源为什么贡献多或少。
- 至少有一条链路能证明热点：媒体报道 + 社区讨论信号，或多个平台同时出现相似讨论。

如果满足这些条件，即使某些网站因为 API、反爬、无主题入口而表现不佳，也可以进入 RAG 阶段。RAG 的任务是验证和组织已有候选，不继续承担“发现更多候选”的职责。

## 进入 RAG 前后的边界

进入 RAG 前继续做：

- 主题入口补充。
- 时间戳详情页回填。
- source health 细分。
- DiscussionProbe 最小实现。
- 候选去重和主题池诊断。

进入 RAG 后做：

- 对候选正文切块。
- 用 metadata 过滤证据：source、theme、time、story cluster。
- claim 级证据检索。
- 旧闻复读 vs 当天 follow-up 对比。
- 历史背景和“自某年以来首次”类补充。

不要让 RAG 做：

- 猜测发布时间。
- 脑补缺失来源。
- 发现全网热点。
- 把社区讨论改写成已确认事实。

## RAG 成熟度分层

RAG 不应一次性从“正文切块”跳到“完整问答”。本项目采用四层成熟度：

### RAG-0：Evidence Scaffold

当前阶段。目标是把已经抓到的正文转成可引用证据：

- `documents.json` 保存候选正文和 metadata。
- `evidence_chunks.json` 保存 chunk、URL、source、time、credibility hint。
- `context_packs.json` 把候选、claim、证据、缺失字段打包。
- 只做关键词/BM25 风格检索和 metadata filter，不急于接向量库。

### RAG-1：Claim-Level Retrieval

加入时机：候选过滤、主题候选池、证据边界和社交热度接口基本稳定后。

目标：

- 每个 claim 检索 3-5 条同事件、同游戏、同时间窗证据。
- 给 `VerificationAgent` 和人工复核提供 compact evidence pack。
- 支持冲突检测、证据不足、因果归因拆分。

进入条件：

- `candidate_url` 与 `retrieved_context` 边界稳定。
- story/candidate/claim id 稳定。
- 至少一轮 live run 能证明候选并非主要卡在采集数量或社交热度缺失。

### RAG-2：Persistent Memory Retrieval

加入时机：多轮 live run 已积累足够 story、claim、evidence、human review。

目标：

- 识别旧闻复读和当天 follow-up。
- 维护 story lifecycle：first_seen、last_seen、confirmed/denied/updated。
- 支持历史背景、纪录候选、爆料源准确率。
- 从 JSON 记忆库升级到 SQLite + FTS/BM25；必要时再接 SQLite-vec、FAISS、Qdrant 或 Chroma。

### RAG-3：News QA Agent

加入时机：EvidenceStore、StoryMemoryStore、SocialHeatStore 和 HumanReviewStore 都有稳定 schema 后。

目标：

- 让用户对已采集材料提问，例如：
  - “过去 48 小时 Switch 2 涨价有哪些证据？”
  - “这个索尼相关流言为什么是待验证？”
  - “某个游戏上一次出现类似争议是什么时候？”
  - “为什么这条新闻入选 Top 10，而另一条没有？”
- 回答必须带引用：story id、claim id、evidence chunk id、source URL、observed_at/published_at。
- 如果证据不足，输出 `insufficient_evidence`，不得凭常识补答案。

## 联想式搜索的时机

联想式搜索应当晚于热点识别。  
例如夏日游戏节开幕时，系统可以扩展“新作首次公布”“新预告”“试玩反馈”“发售日公布”等查询，但前提是已有候选或 DiscussionProbe 证明该事件正在被讨论。

如果在没有热点证据前就做联想搜索，容易扩大普通发布会新闻、内容农场和低价值汇总，最终让系统回到“新闻很多但不热”的状态。

## 下一步建议

短期优先级：

1. 为 listing collector 增加 raw link/time 诊断统计。
2. 对游民星空增加详情页时间回填的低限额实验。
3. 为 IGN/GameSpot/PC Gamer 支持多 feed/listing 入口，并记录每个入口贡献。
4. 实现 DiscussionProbe v0：对 Top 候选做低频查询，只输出讨论证据摘要，不直接改写事实。
5. 当检索诊断稳定后，再进入 RAG 的 claim 级证据检索设计。

## 2026-06-06 v0 实现状态

- `collector_diagnostics.json` 已接入 `search_candidates`，用于记录每个来源的链接数、候选数、缺时间数、重复 URL 数、详情页时间回填数和解析告警数。
- listing collector 已能报告 entry 级诊断。
- 游民星空配置了 `detail_time_backfill_limit: 12`，只对少量缺时间候选尝试详情页时间回填，避免扩大成高频详情页爬取。
- `source_navigation_requests.json` 已接入，默认不调用 LLM；它只把实际观测到的 URL、标题、主题、拒绝原因和诊断摘要交给 SourceNavigator。
- `--run-llm-source-navigator` 会生成 `source_navigation_results.json`。LLM 只能从 `observed_urls` 中推荐入口，解析器会丢弃未观测 URL。

预期效果：

- 下一次 live run 后，可以从 `collector_diagnostics.json` 看出游民星空 `missing_time` 是否因为详情页回填而下降。
- 可以从 `source_navigation_requests.json` 人工检查每个来源实际暴露了哪些可用入口。
- 启用 LLM SourceNavigator 后，可以得到“哪些已观测 URL 更像主题入口/哪些应跳过”的建议，但这些建议只用于改 source 配置，不直接进入事实链路。

## 2026-06-07 live run 结论

两轮真实运行分别为：

- `outputs/langgraph/diagnostics_live/`：不启用 SourceNavigator。
- `outputs/langgraph/navigator_live/`：启用 `--run-llm-source-navigator --llm-source-navigation-limit 3`。

关键观察：

- 检索数量已经基本够用：`main=68`，`supplemental=108/109`，`rejected=166`，主题候选池约 73-74 条。
- 来源连通性不是主要问题：7 个 live 源中 6 个 healthy，Nintendo Official 因 48h 内无入选而 `needs_fill`，不是 blocked。
- 游民星空是最大贡献源，也是最大噪声源：约 435 个链接、76/77 条入池、222/223 个重复 URL、29 条 missing_time、107 条 outside_time_window。
- `detail_time_backfill=0` 说明当前详情页时间回填没有成功降低 missing_time；后续要检查详情页是否没有标准时间 meta，还是 parser 未识别。
- 启用 SourceNavigator 的最终内容几乎没有变化；旧逻辑按 source 配置顺序取前 3 个请求，导致 LLM 看了 Nintendo、PlayStation Blog、Xbox Wire，却没看最需要诊断的游民星空和 IGN。
- 内容质量分数为 71，主要卡在 `discussion_signal_coverage=0.0441`、`no_llm_verification_results` 和单源 story 主导。也就是说现在缺的是“热点/讨论证据”和“语义核查”，不是普通媒体候选数量。
- 补充板块混入了明显非游戏内容，例如 papi 酱宠物用品，需要在游民星空这类综合内容源上继续收紧 `excluded_keywords`，并在后续 story selection 中降低 `manual_review` 补充项的权重。

已据此调整：

- SourceNavigator 请求按诊断痛点排序；用这两轮产物离线重算后，下次 limit=3 会优先看 `gamergen -> nintendo -> ign`。
- live `search_candidates` 内部会打印 source start/done 和 detail time backfill start/done，避免长时间无输出。
- 游民星空新增一组明显非游戏娱乐/带货排除词，先降低综合站补充池污染。

下一步判断：

- 不建议继续盲目增加普通媒体 RSS。候选量已够，继续加普通源会提高去重和噪声压力，却仍不能证明“热点”。
- 检索侧还需要小修：Nintendo 官方源可寻找更及时的地区/新闻入口；游民星空详情页时间回填要确认失败原因；IGN 可继续用 SourceNavigator 检查是否有更窄的 games/news feed。
- 真正的下一阶段应是 DiscussionProbe v0：对主题池 Top 候选生成短查询，低频检查 Bilibili/微博/Reddit/Steam/搜索结果中是否有评论、转发、弹幕、帖子数量或多平台复现。DiscussionProbe 只输出讨论证据，不改写事实。

## 2026-06-08 DiscussionProbe v0

DiscussionProbe v0 的原则：

- 不直接爬取社交平台，不登录账号，不绕过平台限制。
- 先为主题候选生成低频/人工可审计搜索入口，例如 Bilibili、微博、Reddit、Steam、贴吧和小黑盒人工入口。
- 使用已经抓取到的候选正文、摘要和 evidence quotes 识别讨论平台、热议语言、多平台复现和直接互动线索。
- 只提升 `discussion_profile`、`discussion_score`、`discussion_level`；不把“有人讨论”改写成“事实已确认”。
- 合并策略是只升不降：如果候选已有更强的真实互动数据，probe 不会覆盖它。

新增产物：

- `discussion_probe_requests.json`：每个候选的 query、平台搜索入口和使用策略。
- `discussion_probe_report.json`：每个候选的讨论证据、平台、原因、分数和覆盖率汇总。

预期效果：

- `content_quality_report.json` 中的 `discussion_signal_coverage` 会更接近真实正文里已有的讨论线索，不再只依赖候选标题和 RSS/listing 摘要。
- `content_review.md` 中入选 story 的“讨论热度、讨论平台、讨论依据”更可解释。
- 如果 coverage 仍低，说明当前固定媒体源只能证明“新鲜资讯”，不能证明“高热讨论”，下一步需要接真实低频社区搜索或人工打分样本。

限制：

- v0 不能证明微博/B站/贴吧上真的有多少评论或转发；它只是生成入口并利用现有正文证据。
- v0 不处理账号登录型平台和 App-only 数据，例如小黑盒真实热度，需要后续单独做人工/浏览器/平台 API sidecar。
- v0 不应该扩大联想式搜索；联想搜索仍应等某事件已被 DiscussionProbe 或人工确认正在讨论后再启动。

## 2026-06-08 DiscussionProbeProvider v1

v1 的定位：

- 从 `discussion_probe_requests.json` 读取公开搜索入口，按候选数和平台数做低频 HTTP 观测。
- 默认关闭；只有显式传入 `--run-discussion-probe-provider` 才会访问搜索页。
- 写出 `discussion_probe_observations.json`，记录 `ok/blocked/error/skipped_manual`、HTTP 状态、结果标题、`result_count`、`keyword_hit_count`、`discussion_hint_count` 和简短证据文本。
- 不登录平台，不绕过限制，不下载评论详情，不确认事实。

评分原则：

- 单个平台有结果但没有评论/转发/讨论提示，只能算 `weak`，不能提升候选。
- 单个平台有明显评论/转发/讨论提示，或多个平台都有命中，才能进入 `discussed`。
- 多平台命中和讨论提示只证明“值得人工看/可能在讨论”，事实仍由正文证据和 claim verification 决定。
- blocked/error 不是失败结论，而是平台接入方式的诊断信号；如果微博/B站经常 blocked，下一步应考虑人工浏览器 sidecar 或官方/第三方搜索 API。

下一步评估标准：

- 小样本 `--discussion-probe-limit 5 --discussion-probe-provider-platform-limit 2` 能否稳定生成 observations。
- `with_result_signal` 是否明显高于 v0 的正文-only coverage。
- provider 提升的 story 是否真的比普通媒体新闻更接近用户想要的“热点/梗/争议”。
- 如果搜索页大量 blocked 或 JS 空壳，先切换到可审计搜索 API 或浏览器低频观测，不要硬爬。

## 2026-06-08 SearchExpansion v0

当前路线调整：

- 暂停继续细调热度探针评分，先扩大候选发现面。
- SearchExpansion 位于 `search_candidates` 之后、`fetch_documents` 之前。
- 它根据 `source_theme_counts.json` 中的主题缺口生成短查询，低频观测 Bilibili/微博等公开搜索页。
- 有效搜索结果只进入 `supplemental_candidates`，类型为 `discussion_search_lead`；它们是线索，不是事实。
- `discussion_search_lead` 在 claim extraction 中会变成 `search_lead`，规则 verifier 默认拒绝发布，直到后续被权威正文或人工审核确认。

产物：

- `search_expansion_requests.json`：主题、query、平台搜索入口和使用策略。
- `search_expansion_observations.json`：每个搜索入口的状态、结果数、关键词命中、讨论提示和 top results。
- `search_expansion_candidates.json`：从有效 observations 转出的 supplemental 候选。

LLM 使用边界：

- 近期优先让 LLM 做 query 压缩、游戏名/厂商名别名扩展、搜索结果相关性分类。
- 不让 LLM 判断“热不热”，也不让 LLM 补不存在的搜索结果。
- 每轮仍要评估候选数量、主题覆盖、重复率、无关结果比例、provider signals 和 blocked/error。

## 2026-06-08 SearchExpansion v0.1：多方法扩展与爆发日识别

这轮把 SearchExpansion 从单一“主题缺口补 query”扩展成多方法候选发现：

- `theme_gap`：继续按五个主题板块的缺口生成低频查询。
- `candidate_followup`：基于当前候选标题生成跟进查询，用于确认某条媒体新闻是否在社区里被讨论。
- `event_burst`：当候选标题/摘要中出现游戏展、发布会、直面会、Showcase、Summer Game Fest、Xbox Games Showcase 等事件信号，并且同时出现新作、预告、发售日、demo、world premiere、reveal 等新内容信号时，生成发布会/游戏展专项查询。
- `new_content_watch`：在爆发日成立时，补充“新作公布/新预告/发售日/试玩反馈”等通用查询。

爆发日规则的目的不是放松事实门槛，而是放松“日常数量上限”的发现门槛：

- `event_burst` 和 `new_content_watch` 生成的候选会带 `event_context`、`quota_policy=event_burst_briefing_candidate`、`allow_briefing_overflow=true`。
- 这些字段只表示“可进入额外简讯候选池”，不表示可直接发布。
- 产物仍是 `discussion_search_lead`，必须被正文证据、权威源、DiscussionProbe 或人工审核确认后，才能变成正式 story。

## 2026-06-11 主资讯源板块入口策略

当前收集阶段不应继续只依赖“每站一个泛入口”。更好的顺序是：先研究主要站点的稳定板块入口，再把这些入口产出的候选统一进入 `search_candidates -> theme_candidate_pool -> fetch_documents -> DiscussionProbe`。

原则：

- 板块入口只提高主题命中率，不直接证明新闻重要。
- 每个入口要记录 `source_entry_url`、`source_entry_label`、`source_entry_theme`，方便后续诊断“到底是哪一个入口带来噪声”。
- 站点页面如果会 403、JS 空壳、无时间戳，先标为不适合普通 HTTP collector，不强行作为主入口。
- 后续质量评分仍要继续检查 48h、旧闻复读、正文证据、讨论热度和单源集中度。

四个主站当前判断：

- IGN：`https://www.ign.com/news/playstation`、`/news/nintendo`、`/news/xbox`、`/news/pc` 是清晰主题入口。已接入 `article_link_fallback`：当 `<li>` 列表解析不到候选时，只抽取符合 `article_url_patterns` 的 `/articles/` 链接，并解析 IGN 的 `1d/3h` 相对时间。2026-06-12 修正：IGN 列表卡片常把 `3h ago` 放在文章链接旁边而不是链接文本里，因此 article fallback 会在文章 href 附近的 HTML 片段中寻找 `3h ago`、`3 hours ago` 等相对时间，作为列表页时间戳。后续侦查确认普通 `?page=N` 无效，但页面里有隐藏的 `Load More` 链接，例如 `?endIndex=9 -> ?endIndex=19`。因此 IGN 已从静态 `media_listing` 切到通用 `media_incremental_listing`，按页面里的下一页链接继续抓取，不需要先上浏览器。详情页时间回填只保留小额度兜底。
- 游民星空：`https://www.gamersky.com/news/` 页面 HTML 包含 tab 和 `data-nodeid`，但点击栏目/翻页实际通过 JSONP 接口返回列表片段。已把实现从单页 `media_listing` 升级为通用 `media_jsonp_paged_listing`，按 `pagination_url + pagination_entries(node_id)` 抓取多个栏目页，并在页面整体早于 lookback 窗口时停止。collector 命名按“加载机制”而非网站名，后续可复用于同类 JSON/JSONP 列表站点。
- GameSpot：`https://www.gamespot.com/feeds/news/`、`/feeds/game-news/`、`/feeds/reviews/` 这类 RSS 可用；平台页如 `/playstation/`、`/xbox/`、`/nintendo/`、`/pc/` 对普通 urllib 请求会 403。短期继续用 RSS + 后续主题分类，不把 403 平台页作为主 collector。
- PC Gamer：`https://www.pcgamer.com/rss/` 可用；`/news/`、`/games/`、`/hardware/` 是网页栏目但当前普通 HTML 解析器拿不到稳定 article links。它天然服务 PC 板块，不应承担索尼/任天堂/微软主题补源；后续可补 Future/PCGamer 专用 parser。

本轮已实现：

- `SourceConfig` 支持 `feed_entries` / `page_entries`，用于给单个入口标记主题、标签和显示名。
- collector registry 会把入口元数据写入候选：`source_entry_url`、`source_entry_label`、`source_entry_theme`、`theme_section`。
- `ListingCollector` 会读取列表内 `ul[data-nodeid]` 并按 `collector_config.section_node_theme_map` 给候选打主题。
- `ListingCollector` 已支持 `article_link_fallback`，用于 IGN 这类不以 `<li>` 暴露 article card 的页面；文章链接解析已改为栈式处理，避免 IGN 卡片内嵌作者链接时丢失外层文章链接。
- `ListingCollector` 已支持从文章链接附近上下文解析 `3h ago` 这类列表页相对时间；diagnostics 会记录 `article_link_context_time_count`，用于判断是否减少了详情页时间回填压力。
- registry 已支持 `media_incremental_listing`，用于页面中存在 Load More/下一页链接的增量列表；默认识别 `endIndex=N` 形式，并按 max pages / stale page 限制停止。
- registry 已支持 `media_jsonp_paged_listing`，用于 JSON/JSONP 返回 HTML 列表片段的动态分页；配置项包括 `pagination_url`、`request_payload_template`、`pagination_entries`、`max_pages_per_entry` 和 `stale_page_stop_count`。
- registry 已做 URL 级候选合并：同一文章出现在多个主题入口时只保留一条，并记录 `source_entry_themes/source_entry_labels/source_entry_urls`。
- `sources.yaml` 已为游民星空加入 JSONP node 入口配置；`今日推荐`、`单机电玩`、`业界`、`硬件` 等混合栏目不硬写主题，避免跨平台新闻被入口误归类，NS 栏目可以标记 `nintendo`。
- `sources.yaml` 已将 IGN 从泛 RSS 改为四个主题 `page_entries`。

下一步：

1. 用完整 live run 评估 IGN 主题入口是否降低影视/购物混入率，以及是否改善索尼/任天堂/微软/PC 的主题池覆盖。
2. 如果 `source_entry_theme=multiple` 的文章过多，后续在 `classify_candidate_section` 中优先用标题实体和正文证据归类，而不是入口标签。
3. 再评估 GameSpot 是否仅靠 RSS 足够；若不足，再考虑浏览器/Cloudflare 兼容方案，而不是先把 403 页面加入主源。

2026-06-12 英文来源入池/入选诊断：

- `ign_relative_time_live` 显示 IGN 采集已经不是主要瓶颈：raw 67，accepted 32，theme pool selected 14，document fetch selected 3，story candidates 4，final stories 1。
- 主要流失点是三层竞争：
  - `theme_pool_competition`：游民星空等中文源数量和热度语义更强，挤占主题池。
  - `document_fetch_budget_competition`：主题池中有 IGN，但正文抓取预算只选 Top 20，IGN 只抓到少量正文。
  - `story_score_competition`：中文标题/正文中“热议、全网、玩家、争议”等信号更容易抬高 story score，英文来源如果没有讨论证据会落后。
- 新增 `source_selection_diagnostics.json`：以后判断“英文源少”不再只看 final Top 10，而要看 raw/main/theme_pool/fetch/story/final 每层数量。
- 新增 `story_localization_requests.json`：对英文 story 只生成翻译和“已观测中文候选中是否有同事件替代”的 LLM/人工请求包；LLM 不能发明 URL，不能直接改 story 事实状态。
- 本轮还暴露一个后续需要修的问题：个别英文 story 可能把多个不同英文来源证据聚到同一个 story 下，说明 DedupClusterer/StoryRanker 的跨源相似度仍偏粗。进入自动中文替代前，必须先保证 story cluster 足够干净。

这样处理用户提到的场景：如果当天刚好是游戏节、游戏展或厂商发布会，大量新作/新内容确实可能突破日常 10 条或每板块 20 条的普通限制；但突破的前提是“新内容信号 + 事件上下文 + 后续热度/证据确认”，不是凭联想把所有发布会汇总都塞进简报。

## 2026-06-12 RegionalHeatProbe 与证据边界修正

热度验证不能固定为中文平台列表。无论来源是中文、英文，还是后续可能加入的日文，都应优先到该语言/地区常用或热度信号明显的平台寻找讨论证据：

- `zh_cn`：Bilibili、微博、贴吧、小黑盒。
- `en_global`：Reddit、YouTube、Steam、X。
- `ja_jp`：X Japan、YouTube、NicoNico、5ch。
- `global`：在无法判断语言/地区时使用 Bilibili、微博、Reddit、Steam 作为保守混合入口。

新增 `regional_heat.py` 作为接口层，只负责把候选映射到 `heat_region` 和 `search_targets`。它不抓取平台、不调用 LLM、不确认事实。`discussion_probe_requests.json` 会带上 `source_language`、`heat_region` 和对应平台入口，后续 provider、浏览器 sidecar 或人工流程可以按这个结构继续扩展。

同时修正一处证据边界问题：当候选没有抓到自己的正文时，`context_packs` 仍可保留全局检索到的相似 chunk 作为参考上下文，但会标记 `evidence_scope=retrieved_context` 和 `missing_fields=source_document`。`claim_extraction` 不再把这些跨 URL chunk 写入 `source_urls` 或 `evidence_chunk_ids`，避免把 GameSpot/Xbox Wire/IGN 等不同事件的上下文误当作同一条新闻的确定性证据。

后续优先级：

1. 继续让 `DiscussionProbeProvider` 使用 `heat_region`，按地区平台做低频观测。
2. 再做跨语言本地化：英文/日文 story 可生成中文标题和中文替代候选，但替代 URL 必须来自已观察候选。
3. 在上述证据边界稳定后，再细化 story dedup/cluster 的语义合并规则。

## 2026-06-12 regional_heat_live 复盘

`outputs/langgraph/regional_heat_live/` 说明地区热度路由有效，但也暴露了新的优先级：

- 采集量已经足够：raw 707，accepted 472，main 230，supplemental 242，主题候选池达到 100。
- IGN 不是采集瓶颈：raw 67，accepted 32，theme pool 12，document fetch 3，story candidates 3；最终未入选主要因为 story score competition。
- 文档证据边界修复生效：GameSpot 的 Dino Crisis 正文抓取 403，只形成 `evidence_scope=retrieved_context`，对应 claim 被 reject，没有再把相似上下文当成确定性证据。
- 地区热度入口生效：20 个 probe 中 18 个 `zh_cn`、2 个 `en_global`；中文走 Bilibili/微博/贴吧/小黑盒，英文走 Reddit/YouTube/Steam/X。
- 真正的新问题是“非游戏热度被放大”：鹅腿阿姨、滨崎步、梅西表情包、胖东来等社会/娱乐热点能在 Bilibili/微博上有信号，但不应进入游戏资讯简报。

据此新增两条护栏：

- `CandidateTypeGate` 补充真实运行暴露的离题社会/娱乐实体词，把这类内容归为 `off_topic_entertainment`。
- `ClaimExtractor/EvidenceVerifier` 新增 `supplemental_context`：攻略、折扣、泛科技、娱乐八卦、普通补充上下文等即使抓到正文，也不会被规则 verifier 自动标成 `likely`。这类内容只能作为人工/LLM 参考，不进入自动发布 story。

同时 `source_selection_diagnostics.json` 会记录 `document_errors`、`evidence_scope_counts`、`missing_field_counts` 和全局 `evidence_summary`，用于判断某来源是采集少、正文抓取失败、证据降级，还是只是最终排序竞争失败。

## 2026-06-12 社交热度接口与人工/Agent 核查边界

当前 `DiscussionProbeProvider` 能低频观测公开搜索页，但还没有真正接入 Bilibili、小黑盒等更有社交属性的平台数据。后续不应把这个问题伪装成 RAG 或 story score 问题，而应抽象成 `SocialHeatProvider` 接口。

### SocialHeatProvider 目标

统一输出 `social_heat_observations.json`，每条 observation 至少包含：

- `candidate_id` / `candidate_url` / `candidate_title`
- `platform`：如 `bilibili`、`weibo`、`tieba`、`xiaoheihe`、`reddit`、`youtube`、`steam`、`x`
- `access_mode`：`public_search`、`browser_sidecar`、`manual_import`、`api_or_search_service`
- `query`
- `observed_at`
- `status`：`ok`、`blocked`、`login_required`、`manual_required`、`error`
- `result_count`
- `engagement_signals`：播放、评论、弹幕、转发、点赞、帖子数等能拿到的字段；拿不到时显式为空
- `top_results`：标题、URL、snippet、发布时间或平台显示时间
- `heat_validity_hint`：`game_discussion`、`general_social_heat`、`unclear`
- `evidence_texts`：只保存短摘录或可审计摘要，不把搜索页当事实来源

### 平台接入顺序

1. `public_search`：优先用无需登录的公开搜索页或搜索服务，适合 Bilibili、微博公开搜索、Reddit、YouTube、Steam。问题是 JS 空壳、blocked 和结果片段不稳定。
2. `manual_import`：对小黑盒、贴吧某些 App/登录态内容，先允许人工导入搜索结果摘要或截图转写。它不自动化，但能建立高质量人工样本。
3. `browser_sidecar`：当公开 HTTP 搜索不可靠，但浏览器可低频访问时，再用类人工浏览器探针。必须有频率限制、截图/HTML 证据、人工确认开关。
4. `api_or_search_service`：如果后续接入第三方搜索或平台 API，仍输出同一 observation schema，不让下游关心数据来源细节。

2026-06-13 无登录公开入口探测结论：

- 第一批自动化优先级应从 `bilibili` 和 `steam_discussions` 开始。普通 HTTP 能拿到搜索页外壳，适合先验证 `SocialHeatProvider` contract、result_count、top_results、discussion hints 和 evidence_texts。
- `youtube` 与 `x` 普通 HTTP 可能返回 JS 外壳或空 title，不适合作为第一批纯 HTTP provider；后续应走 `browser_sidecar` 或第三方搜索服务。
- `weibo` 普通 HTTP 会返回 Visitor System，`tieba` 和 `reddit` 容易 403，先标记为 `browser_sidecar` / `api_or_search_service` 候选，不把它们当作稳定 public_search。
- `xiaoheihe` 暂无稳定公开搜索页，短期走 `manual_import`，让人工导入搜索结果摘要、截图转写或 App 内观察结论。
- 这些探测只用于选择接入方式，不证明平台长期可抓取，也不代表可以绕过登录、频控或反爬。每个平台 provider 必须把 `status` 写清楚：`ok`、`blocked`、`login_required`、`manual_required` 或 `error`。
- `heat_validity_hint=game_discussion` 只表示搜索结果处在游戏圈语境，不能表示“同一事件”或“事实已验证”。Bilibili 等公开搜索页容易返回同平台/同厂商/同关键词但不同事件的结果；下一层必须用 `RelevanceClassifierAgent` 或人工标签判断 `same_event`、`same_game`、`within_48h` 和 `marketing/clickbait`。

### Deterministic Relevance Gate -> RAG-backed Semantic Gate

下一步不应立刻让 LLM/RAG 判断全部搜索结果，而是先做确定性相关性门：

- `title_entity_overlap`：搜索结果标题是否命中候选中的游戏名、厂商名、平台名、关键事件词。
- `platform_scope_match`：例如 Switch/任天堂、Xbox/微软、PlayStation/索尼、Steam/PC 是否落在同一主题板块。
- `time_hint_match`：搜索页是否能观察到最近一天/最近一周/具体日期；不能观察时标为 `unknown_time`，不直接加分。
- `result_type_guard`：视频、专栏、帖子、商店页、用户页、攻略、带货、泛娱乐结果分开标注。
- `self_reference_removed`：候选标题和 query 本身不得作为搜索结果相关性的证据。

确定性门输出 `social_heat_relevance_checks.json`，每条记录至少包含：

- `candidate_id` / `candidate_url`
- `observation_id` / `platform` / `result_url`
- `deterministic_status`：`likely_same_event`、`same_game_unclear_event`、`same_platform_only`、`off_topic`、`unknown`
- `matched_entities`
- `missing_entities`
- `time_hint_status`：`within_window`、`outside_window`、`unknown_time`
- `result_type`
- `reasons`

只有 `likely_same_event` 或 `same_game_unclear_event + within_window` 才能进入后续语义判断候选。RAG-backed semantic gate 后置：

- 输入：候选正文、搜索结果 observation、top result snippet、已抓取 evidence chunk、story memory。
- 检索：先用 metadata/BM25 找同游戏、同事件、同时间窗证据；RAG-2 后再接历史记忆和向量检索。
- 输出：`semantic_relevance_results.json`，字段包括 `same_event`、`same_game`、`within_48h`、`old_news`、`marketing_or_clickbait`、`confidence`、`evidence_ids`、`missing_evidence`。
- 约束：RAG/LLM 只能判断“这些已观察到的材料是否指向同一事件”，不能新增 URL，不能把社交讨论改成事实确认，不能绕过 `claim_verifications.json`。

2026-06-13 实施状态：

- `LangGraph/src/games_news_agent/social_heat_relevance.py` 已实现第一版确定性门，先用实体/事件词、时间提示、结果类型和 self-reference removal 做低成本筛查。
- `probe_discussions` 已写出 `social_heat_relevance_checks.json`、`semantic_relevance_requests.json`、`semantic_relevance_results.json`。后者当前默认空数组，只作为未来 LLM/RAG 或人工复核结果的落点。
- `content_review.md` 已展示社交相关性检查摘要，方便人工判断这轮热度证据是否可用。
- 当前仍不把相关性检查结果直接接入最终排序；下一轮 live run 要先评估 `same_game_unclear_event` 是否过宽、`unknown_time` 是否过多、英文/中文源是否存在系统性误判。

2026-06-14 `social_heat_relevance_live` 复盘：

- Provider 访问链路能跑通：40 条社交观测全部 `ok`，Bilibili 与微博各 20 条。
- 相关性质量不足：`off_topic=35`、`same_platform_only=5`、`semantic_review_candidates=0`。这代表当前还没有足够样本进入 LLM/RAG 语义核查。
- 主要问题不是“缺 LLM”，而是进入社交探针的候选和 query 过宽。候选里仍有泛娱乐/社会内容，query 保留了媒体标题修饰词，社交搜索容易命中同关键词不同事件。
- 下一步先优化 `DiscussionProbe` 输入过滤、LLM/规则 query compression、平台优先级和 Bilibili/Steam provider。只有当 `semantic_review_candidates` 稳定出现，才把 `semantic_relevance_requests.json` 接给 LLM/人工语义核查。

### 与事实验证的边界

- 社交热度只回答“是否有人正在讨论、讨论是否像同一事件、是否属于游戏圈语境”。
- 社交热度不能把传闻改成事实，不能替代 `claim_verifications.json`。
- 搜索页或评论区只能作为热度/情绪证据，不能作为硬事实证据，除非它本身是官方账号、一手作者或原始发布者。
- 如果 `heat_validity_hint=general_social_heat`，即使平台互动很高，也只能进入人工/LLM 参考池，不能直接提高最终 story 排名。

### 发售日期检索边界

发售日期更新属于结构化事实检索，不属于社交热度：

- `GameReleaseCalendar` 记录各游戏在不同平台、地区、版本上的发售日、发售窗口、延期/改期和已发售确认。
- 官方页面和平台商店优先级最高；权威媒体可以补充；社交平台只提供“大家在讨论延期/发售”的线索。
- 发售日必须保留日期精度：明确日期、月份窗口、季度窗口、年份窗口、TBD、现已推出、突然上架。
- 日期变化要写成事件：`date_confirmed`、`date_changed`、`delayed`、`advanced`、`platform_added`、`region_added`、`released_today`。
- LLM/RAG 可用于自然语言日期归一化、同名游戏消歧和冲突摘要，但不能无来源补日期，也不能覆盖高置信度官方记录。
- 详细策略见 `docs/release_date_strategy.md`。

### 单源主导诊断

游民星空单源主导不能直接判为错误。后续应生成 `source_dominance_audit.json`，把单源优势拆成：

- `volume_advantage`：48h 候选量确实更多。
- `fetch_advantage`：正文抓取成功率更高。
- `language_advantage`：中文标题更容易命中“热议/玩家/争议”等词。
- `real_engagement_advantage`：有真实评论、转发、弹幕、帖子等互动证据。
- `false_heat_advantage`：只有标题热词或站内页面固定文案，没有外部社交证据。
- `noise_advantage`：泛娱乐、社会、科技、带货内容被错误归入游戏主题。

只有 `real_engagement_advantage` 能作为高热度支撑；其它优势只能解释来源贡献，不能单独证明“热点”。

### LLM 与人工语义核查的适合方式

LLM 适合做高语义判断，但必须在结构化输入内工作：

- `EditorialJudgmentAgent`：判断候选是否游戏相关、是否只是公司名伪相关、是否可发布。
- `VerificationAgent`：判断 claim 是否被 evidence 支持，尤其处理流言、因果归因和跨语言同事件。
- `RelevanceClassifierAgent`：判断搜索结果是否同一事件、同一游戏、是否仍在 48h 内有效。
- `RerankAgent`：解释每个主题板块内为什么某些 story 应该排在前面。

人工核查适合作为少量高质量标注：

- 在 `content_review.md` 中看真实 story、证据、热度观察和平台文案。
- 在结构化 `human_semantic_review.json` 中记录 `game_relevance`、`same_event`、`heat_validity`、`publishability`、`style_fit`。
- 把人工标注转成测试样例和 prompt 校准集，而不是每轮临时改规则。
