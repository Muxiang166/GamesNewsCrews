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

## 内容定义

系统优先寻找的不是“所有游戏新闻”，而是 48 小时窗口内值得传播的游戏信息：

- 官方硬新闻：游戏发售、延期、更新、召回、涨价、维护、财报、平台策略。
- 高热讨论：微博、Bilibili、贴吧、小黑盒、TapTap、Reddit 等平台大量讨论的事件。
- 玩家趣闻：离谱操作、聊天截图、游戏内事故、主播名场面、玩家自制梗图。
- 争议事件：价格、DEI、裁员、封号、退款、审核、外挂、服务器事故。
- 梗图素材：高转发图片、视频封面、截图、评论区金句。

硬性过滤：

- `published_at` 或 `observed_at` 必须落在过去 48 小时内。
- 无法确定时间的内容进入待复核区，不直接进入主简报。
- 没有来源 URL 的内容不进入事实结论，只可进入线索池。
- 争议性结论必须至少有两个来源，或一个官方/一手来源。

## LangGraph 主流程

LangGraph 负责编排状态机，LangChain 负责搜索、抓取、检索、LLM 调用等工具层。

```text
Trigger
 -> SourcePlanner
 -> SearchCollector
 -> PageFetcher
 -> AssetExtractor
 -> DedupClusterer
 -> ClaimExtractor
 -> EvidenceVerifier
 -> HeatScorer
 -> StoryRanker
 -> MarkdownEditor
 -> PlatformWriter
 -> LayoutDesigner
 -> ImageRenderer
 -> OpsReviewer
 -> Publisher
```

## 角色与改动计划

### 1. SourcePlanner

职责：决定本轮查哪些来源和关键词。

改动：

- 增加固定来源表：IGN、GameSpot、PC Gamer、Eurogamer、VGC、Gematsu、游民星空、游侠网、3DM、机核、Bilibili、微博、贴吧、小黑盒、TapTap、Reddit、Steam、PlayStation Blog、Xbox Wire、Nintendo。
- 每个来源配置 `kind`、`region`、`priority`、`collector`、`supports_time_filter`。
- 生成站内搜索 query，例如 `site:ign.com game news after:2026-05-09`。

### 2. SearchCollector

职责：获取候选资讯和社区线索。

改动：

- 不再只依赖 DuckDuckGo。
- 优先接入支持结构化结果的搜索服务，如 Tavily、Brave Search、SerpAPI、Bing Search，后续按可用性选择。
- 对固定站点优先使用 RSS、站内页面、API 或稳定页面规则。
- 搜索结果统一成 `SearchCandidate` JSON。

### 3. PageFetcher

职责：抓取网页正文和元数据。

改动：

- 抽取标题、正文、发布时间、作者、canonical URL、图片、视频封面。
- 对 Bilibili、微博、小黑盒等动态内容预留浏览器抓取接口。
- 保存 `raw_sources.jsonl`，以后可复盘每条结论来自哪里。

### 4. AssetExtractor

职责：提取可排版素材。

改动：

- 提取文章图、视频封面、OG image、玩家截图、梗图 URL。
- 标记版权/来源风险。
- 读取不到素材时生成 `manual_fill_required=true`。

### 5. DedupClusterer

职责：去重和聚类。

改动：

- 先按 canonical URL 去重。
- 再按标题相似度、实体、时间、来源聚类。
- 同一事件保留多个来源作为证据，而不是丢弃。

### 6. ClaimExtractor

职责：将资讯拆成可验证声明。

改动：

- 每个故事拆成 1-5 个 claim。
- claim 必须包含主体、动作、时间、对象、数值或状态。
- 不可验证的情绪表达单独放入 community_sentiment。

### 7. EvidenceVerifier

职责：去伪存真。

改动：

- 对每个 claim 输出 `verified`、`likely`、`rumor`、`conflict`、`reject`。
- 官方源权重最高，媒体源次之，社区源用于发现热度和玩家情绪。
- 对 DEI、亏损、涨价等因果性强的话题，必须区分“事实发生”和“原因推断”。

### 8. HeatScorer

职责：判断是否值得写。

改动：

- 热度分 = 来源优先级 + 互动数 + 转发/评论速度 + 多平台传播 + 话题新鲜度。
- 没有互动数据时，用多源密度和社区出现频率做弱替代。
- 低热度但高重要性的官方新闻可保留，但不放在社媒头条。

### 9. MarkdownEditor

职责：生成可读简报。

改动：

- Markdown 必须引用证据编号。
- 每条新闻包含：标题、发生时间、热度原因、证据链、可信度、素材状态。
- 输出同时生成机器可读 JSON。

### 10. LayoutDesigner

职责：把内容转成版面设计，不负责文生图。

改动：

- 输出 `layout_manifest.json`。
- 定义微博长图、小红书轮播、Bilibili 动态图等画布尺寸。
- 每个内容块绑定真实素材 URL 或 `manual_fill_required` 占位。

### 11. ImageRenderer

职责：像 Word 导出 PDF 一样渲染图片。

改动：

- 优先使用 HTML/CSS + Playwright 截图。
- 后续可补 Pillow/ReportLab 做备用渲染。
- 不用 LLM 生成图，只用抓取到的真实图、截图、封面和模板排版。

### 12. OpsReviewer / Publisher

职责：发布前审核和运营。

改动：

- 第一阶段只生成发布包，不自动发布。
- 第二阶段做半自动发布清单。
- 第三阶段再考虑接微博、小红书、Bilibili 发布能力。

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
- 实现来源可信度评分。
- 实现热度评分。

### Phase 4：内容生产

- 输出 Markdown 简报。
- 输出微博、小红书、Bilibili 文案。
- 输出素材缺失报告。

### Phase 5：排版成图

- 实现 HTML/CSS 模板。
- 使用 Playwright 渲染 PNG。
- 每条图都有可追溯素材来源。

### Phase 6：内容运营

- 先半自动发布。
- 再按平台能力接自动发布。
