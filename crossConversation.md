# GamesNewsCrew / LangGraph 进入真正 Agent 设计阶段的评估与后续设计草案

> 创建目的：把当前项目的阶段评估、事件驱动式 LangGraph 重构方向、状态模型扩展方案，以及后续加入新思路的方法，集中沉淀到一个跨对话可复用文档中。

---

## 0. TL;DR

结论：**可以进入真正的 agent 设计阶段**，但最合理的进入方式不是立刻做“很多自由对话式 agent”，而是先做：

- **事件驱动（event-driven）的 LangGraph 编排**
- **状态驱动（state-driven）的条件分流**
- **按事件类型进入不同子图（subgraph）**
- **让 LLM 只进入高语义判断节点，不进入确定性前置节点**

更准确地说，当前项目已经适合进入：

> **agent architecture design phase**

但还不适合直接切到：

> **fully autonomous multi-agent production phase**

---

## 1. 当前项目是否已经具备进入 agent 设计阶段的条件？

### 1.1 结论

**是，已经具备。**

原因不是“因为已经用了 LangGraph”，而是因为项目已经具备了真正 agent 化所需要的四个基础条件：

1. **有明确的主链路骨架**
2. **有稳定的 state / artifact 合同**
3. **有 LLM 进入边界意识**
4. **有质量评估与回放闭环**

---

### 1.2 已具备的基础

#### A. 主链路已经清晰，不再是纯概念阶段

当前主图已经形成较完整的链路：

- `plan_sources`
- `search_candidates`
- `expand_search_candidates`
- `fetch_documents`
- `probe_discussions`
- `extract_assets`
- `deduplicate_stories`
- `extract_claims`
- `verify_claims`
- `score_heat`
- `write_platform_posts`
- `validate_content_quality`
- `write_content_review_pack`
- `write_material_bundle`
- `draft_markdown`
- `design_layout`
- `render_assets`

这说明项目已经不是“想做什么 agent”的阶段，而是已经进入“如何编排已有能力模块”的阶段。

参考：
- `LangGraph/src/games_news_agent/graph.py`
- `LangGraph/src/games_news_agent/nodes.py`

#### B. PipelineState 已经很丰富

当前 `PipelineState` 已经承载了：

- 候选层：`candidates` / `supplemental_candidates` / `rejected_candidates`
- 文档层：`documents` / `document_errors`
- 证据层：`evidence_chunks` / `context_packs`
- 断言层：`claims` / `claim_verifications`
- Story 层：`stories` / `story_candidates` / `theme_sections`
- 包装层：`platform_posts` / `material_bundle`
- 诊断层：`source_theme_counts` / `collector_diagnostics` / `discussion_probe_report`
- 质量层：`content_quality_report`

这说明项目已经具备“状态编排”的条件。

参考：
- `LangGraph/src/games_news_agent/schemas.py`

#### C. LLM 边界已经想清楚了

项目 roadmap 已明确：

LLM 不应负责：
- RSS / 网页抓取
- 48h 时间窗
- URL 过滤
- 候选分流
- JSON 持久化

LLM 应进入：
- ClaimExtractor
- EvidenceVerifier
- HistoricalContextMiner
- MarkdownEditor / PlatformWriter
- LayoutDesigner

这说明系统已经从“多加一些 agent”进化到“把 agent 放在正确的位置”。

参考：
- `docs/roadmap.md`

#### D. 已经有可评价的质量门

`content_quality.py` 已经有阶段评分和 gate 概念：

- `source_collection`
- `candidate_filtering`
- `evidence_fetch`
- `claim_verification`
- `story_selection`
- `platform_packaging`

这意味着未来 agent 化以后，可以通过指标验证是否真的更好，而不是靠主观感觉判断。

参考：
- `LangGraph/src/games_news_agent/content_quality.py`

---

## 2. 为什么现在还不应该直接“全面自由 agent 化”

虽然已经适合进入 agent 设计阶段，但当前还不适合直接把主链路改造成自由协商式、多人格式、多 agent 自治系统。

### 2.1 当前主图本质上仍然是线性 pipeline

当前 `build_graph()` 基本是单链 `add_edge(...)`，还没有显式的：

- 条件分支
- 失败回路
- 人工复核分支
- 事件专用子图
- 升级路径

所以现阶段更准确地说，它是：

- **结构化 pipeline**

而不是：

- **事件驱动 agent graph**

### 2.2 现在的 state 更像 artifact 仓库，还不是决策状态机

当前 `PipelineState` 很强，但多数是：

- 文件路径
- artifact 列表
- 运行参数
- 诊断结果

它已经能存结果，但还没有充分表达“如何决策下一步”的字段，比如：

- `event_type`
- `verification_policy`
- `review_required`
- `publishability`
- `routing_decision`
- `escalation_reason`

### 2.3 当前节点多数是功能节点，不是事件节点

例如：

- `probe_discussions`
- `verify_claims`
- `score_heat`

这些节点已经代表能力模块，但还不是：

- “rumor 事件怎么走”
- “官方公告怎么走”
- “玩家热梗怎么走”
- “follow-up update 怎么走”

因此，下一步最重要的不是加更多节点，而是把已有节点用**事件路由逻辑**重新编排。

---

## 3. 推荐的总方向：从线性流水线升级为事件驱动式 Agent Graph

推荐目标不是“更多 agent”，而是：

> **状态驱动 + 事件分型 + 条件路由 + 子图编排**

### 3.1 推荐设计原则

1. **先事件化，再人格化**
2. **先状态合同，再 prompt 合同**
3. **先条件路由，再多 agent 自由协商**
4. **先把主链路变成可分支图，再考虑创作型 sidecar**

### 3.2 推荐的两层图结构

#### 第一层：Discovery / Intake Graph

职责：
- 拉来源
- 候选过滤
- 候选分流
- 讨论探测
- 初步聚类
- 形成候选事件 work item

这一层尽量保持偏确定性。

#### 第二层：Per-Event Agent Graph

职责：
- 对每个事件单独决策
- 根据事件类型走不同验证 / 写作 / 复核路径
- 最后再合并成 story selection 与包装结果

这种两层结构比“一条大链里混合所有事件”更适合项目未来扩展。

---

## 4. A：基于当前代码的事件驱动 LangGraph 重构方案

这一部分回答：

> 如果现在正式开始做 agent 设计，应该怎么改？

---

### 4.1 重构目标

把当前图从：

- 批次式、线性主链路

升级为：

- 事件路由式、可分支、可升级、可待审的 agent graph

---

### 4.2 建议新增的核心节点

#### 1. `build_event_work_items`

职责：
- 从 `context_packs`、`story_clusters`、`discussion_profile`、`claim metadata` 中生成标准化事件对象
- 给每个事件打上初始 `event_type`、`priority`、`verification_policy`

输入：
- `candidates`
- `supplemental_candidates`
- `context_packs`
- `story_clusters`
- `discussion_probe_report`

输出：
- `event_work_items`

#### 2. `route_event_work_items`

职责：
- 根据 `event_type`、`discussion_level`、`source_mix`、`freshness`、`claim_type`、`memory_status` 决定走哪条子图

输出：
- `event_routes`
- 或者直接按 lane 拆分：
  - `official_event_items`
  - `rumor_event_items`
  - `discussion_event_items`
  - `followup_event_items`

#### 3. `merge_event_results`

职责：
- 将不同子图的输出统一汇总
- 重新落回 story / publishing / review 的统一结构

输出：
- `event_results`
- `stories`
- `review_queue`

#### 4. `route_review_queue`

职责：
- 将高风险 story、流言、冲突证据 story、素材不足但潜力高的 story 单独分流

输出：
- `ready_stories`
- `needs_human_review`
- `blocked_stories`

---

### 4.3 建议拆分或改造的现有节点

#### `extract_claims`
建议演进为两层：
- `extract_event_claims`
- `normalize_claim_packages`

原因：不同事件类型的 claim 粒度不应完全一致。

例如：
- 官方更新类：更适合结构化 claim
- 社区热议类：要区分“事实 claim”和“讨论 claim”
- 流言类：要区分“爆料内容”与“传播状态”

#### `verify_claims`
建议拆为：
- `verify_official_claims`
- `verify_rumor_claims`
- `verify_discussion_signals`
- `merge_verification_results`

原因：不同事件的 verification policy 明显不同。

#### `score_heat`
建议拆为：
- `score_event_priority`
- `score_publishability`
- `rank_story_candidates`

原因：热度、可发布性、最终排序不是同一个问题。

#### `write_platform_posts`
建议后移到 review 路由之后，或者至少只对：
- `ready`
- `needs_review_but_worth_drafting`

的事件生成平台文案。

否则容易为后续会被 reject 的内容浪费 token / 产物噪声。

---

### 4.4 建议改动的关键文件

#### `LangGraph/src/games_news_agent/schemas.py`
新增：
- `EventWorkItem`
- `RoutingDecision`
- `ReviewQueueItem`
- `EventResult`
- 扩展 `PipelineState`

#### `LangGraph/src/games_news_agent/graph.py`
改造成：
- 条件边
- 子图入口
- merge 节点
- review route

#### `LangGraph/src/games_news_agent/nodes.py`
新增：
- `build_event_work_items`
- `route_event_work_items`
- `merge_event_results`
- `route_review_queue`
- 若干事件专用 verify / enrich 节点

#### `LangGraph/src/games_news_agent/story_ranking.py`
从“story score 计算模块”升级为：
- 事件结果的最终排名器
- 可结合 `event_type` 与 `review state`

#### `LangGraph/src/games_news_agent/content_quality.py`
增加：
- 各事件类型覆盖率
- 不同子图的表现评分
- review queue 健康度

---

### 4.5 推荐实施顺序

#### 第一步：先不改功能，只加中间状态对象
目标：让 graph 先有“事件层表达能力”。

#### 第二步：加 `build_event_work_items` 与 `route_event_work_items`
目标：先分类，不急着大改后续。

#### 第三步：先落地 3 个子图
- `official_update`
- `rumor_claim`
- `hot_discussion`

#### 第四步：增加 review queue
目标：把“待审 / ready / blocked”作为显式状态，而不是隐式判断。

#### 第五步：再逐步扩到
- `player_story`
- `controversy_or_market`
- `review_score`
- `follow_up_update`

---

## 5. C：建议中的新 Graph 拓扑图

这一部分把前面的思路画成可执行的结构。

---

### 5.1 推荐版主图（概念层）

```text
plan_sources
 -> search_candidates
 -> expand_search_candidates
 -> fetch_documents
 -> probe_discussions
 -> extract_assets
 -> deduplicate_stories
 -> build_event_work_items
 -> route_event_work_items

route_event_work_items
  -> official_event_subgraph
  -> rumor_event_subgraph
  -> hot_discussion_subgraph
  -> player_story_subgraph
  -> controversy_event_subgraph
  -> followup_event_subgraph
  -> supplemental_or_reject_lane

all event subgraphs
 -> merge_event_results
 -> score_publishability
 -> route_review_queue

route_review_queue
  -> write_platform_posts_ready_lane
  -> write_platform_posts_review_draft_lane
  -> human_review_queue_lane
  -> blocked_lane

write_platform_posts_ready_lane
 -> validate_content_quality
 -> write_content_review_pack
 -> write_material_bundle
 -> draft_markdown
 -> design_layout
 -> render_assets

write_platform_posts_review_draft_lane
 -> validate_content_quality
 -> write_content_review_pack
 -> write_material_bundle
 -> draft_markdown

human_review_queue_lane
 -> write_content_review_pack
 -> write_material_bundle

blocked_lane
 -> write_content_review_pack
```

---

### 5.2 更贴近 LangGraph 的分阶段设计

#### Phase A：Discovery
```text
plan_sources
 -> search_candidates
 -> expand_search_candidates
 -> fetch_documents
 -> probe_discussions
 -> deduplicate_stories
```

#### Phase B：Eventization
```text
deduplicate_stories
 -> build_event_work_items
 -> route_event_work_items
```

#### Phase C：Per-Event Handling
```text
route_event_work_items
 -> official_event_subgraph
 -> rumor_event_subgraph
 -> hot_discussion_subgraph
 -> followup_event_subgraph
```

#### Phase D：Merge & Review
```text
merge_event_results
 -> score_publishability
 -> route_review_queue
```

#### Phase E：Packaging
```text
ready_lane -> write_platform_posts -> validate_content_quality -> draft_markdown
review_lane -> write_platform_posts -> write_content_review_pack
blocked_lane -> write_content_review_pack
```

---

### 5.3 推荐优先实现的 3 条子图

#### 子图 1：Official Update

```text
official_event_subgraph:
  normalize_official_claims
   -> verify_official_claims
   -> build_official_event_result
```

适合处理：
- 发售
- 延期
- 补丁
- 财报
- 维护
- 价格公告

特点：
- 确定性强
- 对讨论信号依赖较低
- 对结构化事实依赖高

---

#### 子图 2：Rumor Claim

```text
rumor_event_subgraph:
  normalize_rumor_claims
   -> cross_source_rumor_check
   -> llm_rumor_verification
   -> rumor_publishability_gate
   -> build_rumor_event_result
```

特点：
- 必须强制更严格 verification policy
- 不能默认 ready
- 对 `needs_review` / `blocked` 分流非常关键

---

#### 子图 3：Hot Discussion

```text
hot_discussion_subgraph:
  enrich_discussion_evidence
   -> verify_discussion_support
   -> separate_fact_vs_sentiment
   -> build_discussion_event_result
```

特点：
- 重点不是“事件发生了没”，而是“是不是正在热议”
- 需要把事实结论和传播结论分开

---

## 6. B：状态模型扩展方案（增强版）

这一部分是对之前 B 的扩展和深化。

核心思想：

> 不要继续只把 `PipelineState` 当成 artifact 大仓库，而要引入“事件生命周期对象”。

---

### 6.1 为什么要从大 State 转向中间领域对象

如果所有字段都继续堆进 `PipelineState` 顶层，会出现问题：

1. 语义混杂：运行参数、产物路径、业务决策混在一起
2. 扩展困难：每新增一种事件，都要给顶层 state 再加一堆字段
3. 路由不清晰：很难表达“这个 story 正在 rumor lane、那个在 review lane”
4. 测试困难：无法对单个事件生命周期做单元测试

所以建议引入“领域对象”，由 `PipelineState` 持有这些对象集合。

---

### 6.2 建议新增的核心对象

#### 6.2.1 EventWorkItem

这是最重要的新增对象。它代表：

> “一个正在被系统处理的事件单元”

建议字段：

```python
class EventWorkItem(BaseModel):
    event_id: str
    event_type: Literal[
        "official_update",
        "rumor_claim",
        "hot_discussion",
        "player_story",
        "controversy_or_market",
        "review_score",
        "follow_up_update",
        "supplemental_lead",
    ]
    story_cluster_id: str | None = None
    source_candidate_urls: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    source_kinds: list[str] = Field(default_factory=list)
    primary_title: str = ""
    title_variants: list[str] = Field(default_factory=list)
    freshness_bucket: Literal[
        "within_6h",
        "within_24h",
        "within_48h",
        "older_but_followup",
    ] = "within_48h"
    memory_status: str | None = None
    discussion_level: Literal["none", "weak", "discussed", "trending"] = "none"
    discussion_score: float = 0.0
    source_diversity_score: float = 0.0
    evidence_strength: float = 0.0
    risk_level: Literal["low", "medium", "high"] = "medium"
    verification_policy: Literal[
        "light",
        "standard",
        "strict_rumor",
        "discussion_first",
        "manual_review_first",
    ] = "standard"
    routing_decision: str = "pending"
    review_required: bool = False
    review_reason: str | None = None
    publishability: Literal[
        "unknown",
        "draftable",
        "ready",
        "needs_review",
        "blocked",
    ] = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)
```

作用：
- 给 graph 一个真正可路由的中间对象
- 让每个事件可以独立推进状态

---

#### 6.2.2 RoutingDecision

用途：记录为什么进入某个子图。

```python
class RoutingDecision(BaseModel):
    event_id: str
    route: Literal[
        "official_lane",
        "rumor_lane",
        "discussion_lane",
        "player_story_lane",
        "followup_lane",
        "supplemental_lane",
        "blocked_lane",
    ]
    reason: str
    confidence: float = 0.0
    requires_llm_verifier: bool = False
    requires_human_review: bool = False
    fallback_route: str | None = None
```

作用：
- 提高可解释性
- 方便 debugging
- 方便后续离线回放“为什么这个事件走这条线”

---

#### 6.2.3 ReviewQueueItem

用途：显式表达“进入人工/半人工复核的项目”。

```python
class ReviewQueueItem(BaseModel):
    event_id: str
    story_id: str | None = None
    review_type: Literal[
        "rumor_verification",
        "single_source_risk",
        "conflicting_evidence",
        "insufficient_discussion_support",
        "asset_gap",
        "editorial_value_check",
    ]
    severity: Literal["info", "warning", "error"] = "warning"
    reason: str
    recommended_action: str
    blocking: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
```

作用：
- 让 review 变成显式状态，而不是散落在 notes / issues 中
- 可进入后续 UI、审核面板、人工标注工作流

---

#### 6.2.4 EventResult

用途：每条事件子图跑完后的标准化输出。

```python
class EventResult(BaseModel):
    event_id: str
    event_type: str
    story_id: str | None = None
    final_status: Literal["ready", "needs_review", "blocked", "supplemental"]
    publishability_score: float = 0.0
    verification_summary: dict[str, Any] = Field(default_factory=dict)
    discussion_summary: dict[str, Any] = Field(default_factory=dict)
    writing_inputs: dict[str, Any] = Field(default_factory=dict)
    review_queue_items: list[ReviewQueueItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

作用：
- 所有子图统一输出格式
- 后续 merge 和 ranking 简化

---

#### 6.2.5 StoryLifecycleState

用途：描述 story 从候选到发布准备的生命周期。

```python
class StoryLifecycleState(BaseModel):
    story_id: str
    current_stage: Literal[
        "candidate",
        "eventized",
        "verified",
        "ranked",
        "drafted",
        "review_ready",
        "layout_ready",
        "blocked",
    ]
    last_transition: str = ""
    next_expected_action: str = ""
    owner_lane: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
```

作用：
- 避免 story 在主链路里“状态跳跃但不可见”
- 以后方便做 dashboard 和 debug trace

---

### 6.3 建议在 PipelineState 里新增的集合字段

```python
class PipelineState(TypedDict, total=False):
    ...
    event_work_items: list[dict[str, Any]]
    routing_decisions: list[dict[str, Any]]
    review_queue: list[dict[str, Any]]
    event_results: list[dict[str, Any]]
    story_lifecycle_states: list[dict[str, Any]]
```

这样顶层 state 仍然是 LangGraph 的共享状态，但业务复杂度会收敛到领域对象里。

---

### 6.4 推荐的“事件类型”枚举（第一版）

建议先控制在 7~8 类，不要一开始拆得过细。

第一版推荐：

1. `official_update`
2. `rumor_claim`
3. `hot_discussion`
4. `player_story`
5. `controversy_or_market`
6. `review_score`
7. `follow_up_update`
8. `supplemental_lead`

#### 不建议第一版就拆太细的原因

如果上来就拆成十几二十种类型：
- 路由规则会不稳定
- 边界会大量重叠
- 测试样本不够
- 指标无法对齐

更好的做法是：

- 先少量高价值类型
- 通过真实 run 观察高频误判
- 再逐步细分

---

### 6.5 推荐的 verification policy 抽象

除了 `event_type`，另一个很关键的中间抽象是：

> **verification_policy**

因为并不是所有分流都必须由类型决定。

例如：
- 同样是“官方更新”，如果只有单源且时间不完整，也可能进入 `manual_review_first`
- 同样是“热议事件”，如果有多平台讨论但事实 claim 弱，可能是 `discussion_first`
- 同样是“流言”，如果来源极强且有二次佐证，也可能仍是 `strict_rumor` 但优先级更高

推荐 policy：
- `light`
- `standard`
- `strict_rumor`
- `discussion_first`
- `manual_review_first`

这会比只看 `event_type` 更灵活。

---

### 6.6 推荐的“风险维度”抽象

未来如果系统越来越复杂，建议把“为什么需要 review”从单个字段继续结构化。

例如：

```python
class RiskProfile(BaseModel):
    factual_risk: float = 0.0
    source_risk: float = 0.0
    rumor_risk: float = 0.0
    discussion_evidence_risk: float = 0.0
    editorial_noise_risk: float = 0.0
    asset_gap_risk: float = 0.0
```

这样后续 review route 会比简单 `review_required=True` 更强。

---

### 6.7 如何判断某个新状态对象是否值得引入？

未来不要因为“想到一个概念”就立刻加字段。

推荐用下面四问判断：

1. **它是否会改变路由？**
2. **它是否会改变验证策略？**
3. **它是否会改变 review / publish 决策？**
4. **它是否值得单独被测试与回放？**

如果四问里至少满足两条，通常值得抽成显式状态对象或字段。

---

## 7. 未来如果又意识到一个“应该加入的思路”，该怎么做？

这一部分是给未来自己的操作指南。

核心建议：

> **不要直接把“新思路”写成新节点或新 prompt；先判断它属于哪一层，再决定落在哪个对象、节点、路由或评估项上。**

---

### 7.1 先把新思路归类到四个层次之一

未来想到一个新想法时，先问：

#### 类型 1：Discovery 层新思路
例子：
- 新来源
- 新的 SearchExpansion 方法
- 新的平台热度入口
- 时间回填机制

应该落在：
- source config
- collector
- diagnostics
- candidate enrichment

#### 类型 2：Eventization 层新思路
例子：
- 新事件类型
- 新的 route 规则
- 新的 follow-up 识别法
- 新的 discussion signal 归因方式

应该落在：
- `EventWorkItem`
- `RoutingDecision`
- route node

#### 类型 3：Verification / Review 层新思路
例子：
- 新的 rumor 分级
- 新的冲突证据处理
- 多语言证据交叉验证
- 是否需要强制人工复核

应该落在：
- `verification_policy`
- `ReviewQueueItem`
- event subgraph

#### 类型 4：Packaging / Editorial 层新思路
例子：
- 标题风格分型
- 平台文案模板
- layout 内容块策略
- 长图结构建议

应该落在：
- writing inputs
- platform writer
- layout designer
- creative sidecar

---

### 7.2 用“最小落地点”原则落地

所谓最小落地点：

> **一个新想法，先只找一个最能承载它的位置，不要一次改 6 个地方。**

例如：

#### 想法：
“夏日游戏节这种事件日应该走特殊逻辑。”

不要立刻：
- 改 collector
- 改 ranking
- 改 prompt
- 改 layout
- 改 review

而是先把它落在：
- `event_context`
- `event_type = event_burst_related`
- 或 `verification_policy = discussion_first`

让它先以**一个可观察字段**存在。

只有当它反复证明有效，再扩散到更多节点。

---

### 7.3 新思路进入系统的推荐流程

推荐 6 步：

#### Step 1：写成一句清晰陈述
格式建议：

- “我怀疑 X 类事件应该使用 Y 路由。”
- “我怀疑 Z 信号应该影响 review，而不是 ranking。”
- “我怀疑这个能力属于 verification 层，而不是 discovery 层。”

#### Step 2：判断它改变什么
勾选一项或多项：
- 改变候选发现
- 改变事件分类
- 改变验证策略
- 改变人工复核
- 改变文案包装
- 改变质量评分

#### Step 3：决定最小落地点
从以下里面选一个：
- 新字段
- 新中间对象字段
- 新 route 规则
- 新子图节点
- 新质量指标
- 新 diagnostics artifact

#### Step 4：先加到 replay / dry-run 可观测层
优先让它出现在：
- artifact
- content review
- diagnostics
- quality report

而不是先做成“自动生效但不可见”的黑盒逻辑。

#### Step 5：用 2~5 个真实 run 检查它有没有价值
看它是否：
- 提升 quality score
- 降低误入选
- 提高 discussion coverage
- 降低单源主导
- 减少 rumor 风险

#### Step 6：只有在有收益后，再正式固化进主链路
这时再考虑：
- schema 固化
- 节点固定
- prompt 更新
- UI / review 工作流接入

---

### 7.4 推荐建立一个“新思路收纳格式”

未来每次想到新思路，不要散落在聊天记录里。建议统一沉淀成这种结构：

```markdown
## Idea: <short-name>

### Hypothesis
一句话描述新思路。

### Why it may matter
它可能改善什么问题。

### Layer
Discovery | Eventization | Verification | Packaging

### Minimal insertion point
最小落地点：字段 / 节点 / 子图 / artifact / report

### Observable output
加入后应该在哪个 artifact 或 report 中看到痕迹。

### Success metric
如何判断它有效。

### Promotion rule
满足什么条件后，升级为主链路正式逻辑。
```

这个模板非常重要，因为它会防止系统被“想到什么就加什么”的冲动拖坏。

---

### 7.5 什么时候一个新思路应该只是注释 / backlog，而不该立刻编码？

以下情况建议先放 backlog：

1. 没有可观察输出
2. 不能明确归类到某一层
3. 无法说明它会改善哪一项质量指标
4. 它和已有逻辑高度重叠
5. 它只是 prompt 灵感，不是系统结构变化

判断标准很简单：

> 如果这个思路今天加进代码，明天你却无法从 artifact 中看出它是否起作用，那它就还不该立刻编码。

---

### 7.6 如何避免“越想越复杂”

未来最容易出现的风险不是“没想法”，而是“思路太多，系统过早复杂化”。

推荐以下约束：

#### 约束 1：一轮只引入一个结构性新概念
比如只引入：
- `EventWorkItem`

不要同时再引入：
- 5 个新 graph 子图
- 3 套新 prompt
- 2 套新 review 机制

#### 约束 2：先把新思路变成可观察字段，再变成强逻辑
先让它出现在 artifact 中，后让它影响 route / publish。

#### 约束 3：先服务于 quality gate，再服务于“看起来更智能”
如果一个想法只是让系统“更像 agent”，但不能改善质量门，优先级就应该靠后。

#### 约束 4：优先补“决策结构”，不是补“修辞能力”
当前阶段主问题仍然是：
- 什么内容值得走哪条线
- 什么必须待审
- 什么应该 blocked

而不是“如何写得更像人”。

---

## 8. 一个实用的未来工作法：把新思路挂到四个固定入口上

未来任何新想法，优先问它应该挂到下面哪一个入口：

### 入口 A：新字段
如果它首先是“一个状态”。

例：
- `event_burst_context`
- `followup_delta_detected`
- `community_proof_strength`

### 入口 B：新 route 规则
如果它首先改变“走哪条子图”。

例：
- 多平台讨论 > 某阈值，走 `discussion_lane`
- 爆料 + 单源，走 `strict_rumor`

### 入口 C：新 review 类型
如果它首先改变“是否需要人工看”。

例：
- `cross_language_conflict`
- `suspicious_single_source_high_heat`

### 入口 D：新质量指标
如果它首先改变“如何评价结果是否更好”。

例：
- `event_route_accuracy`
- `review_queue_precision`
- `followup_detection_precision`

这四个入口会极大减少系统混乱。

---

## 9. 当前最推荐的落地优先级

### Priority 1
引入 `EventWorkItem`、`RoutingDecision`、`ReviewQueueItem`

### Priority 2
新增：
- `build_event_work_items`
- `route_event_work_items`
- `merge_event_results`
- `route_review_queue`

### Priority 3
先实现 3 条子图：
- official
- rumor
- hot discussion

### Priority 4
把 `content_quality_report` 扩展到：
- 各事件类型覆盖率
- 路由质量
- review queue 健康度

### Priority 5
再考虑更创作型的 sidecar：
- creative pitch
- layout critique
- tone suggestion

---

## 10. 最终总结

### 10.1 这份评估的核心结论

**GamesNewsCrew 现在已经可以进入真正的 agent 设计阶段。**

但“真正的 agent 设计”在这个项目里最合理的含义不是：

- 做更多拟人角色
- 做更多自由协商 agent
- 让 LLM 接管前置确定性流程

而是：

- 把 LangGraph 主链路升级为**事件驱动式状态图**
- 把现有 artifact state 升级为**决策 state + 生命周期对象**
- 让不同事件走不同子图
- 让 review / blocked / ready 成为一等状态
- 让后续所有新思路都通过“可观察、可回放、可评分”的方式进入系统

### 10.2 一句话建议

> **先做 event-driven orchestration，再做自由 multi-agent；先做状态设计，再做 prompt 设计；先做 review-aware graph，再做创意 sidecar。**

---

## 11. 可直接作为下一轮设计输入的短版清单

### 立刻可做
- 新增 `EventWorkItem`
- 新增 `RoutingDecision`
- 新增 `ReviewQueueItem`
- 在 `graph.py` 引入条件路由
- 先做 3 条事件子图：official / rumor / discussion

### 暂时不要急着做
- 全面自由 agent 协商
- 大量人格化 agent
- 让 LLM 接手 deterministic 节点
- 为所有事件类型一次性做过细拆分

### 未来每次有新想法时
先问：
1. 它属于哪一层？
2. 它改变什么决策？
3. 它最小落在哪？
4. 它如何可观察？
5. 它如何通过质量门验证有效？

如果这五问答不出来，先不要编码，先记成 idea note。

---

## 12. LangChain / LangGraph / LangSmith 的区别，以及在本项目中的对应分层

这一部分融合最新一轮讨论，目的是把三个概念在 GamesNewsCrew 里的位置彻底讲清楚。

### 12.1 最简区别

可以把三者理解成三个不同层次的问题：

- **LangChain**：怎么调用模型、检索、工具，并在单个节点内部完成具体能力
- **LangGraph**：这些节点如何围绕共享状态组成工作流、分支、子图和 agent 编排
- **LangSmith**：这个工作流跑得怎么样，如何观测、调试、评估、比较和沉淀反馈

如果只用一句话概括本项目当前状态：

> **GamesNewsCrew 已经有了 LangGraph 主骨架，也有一部分 LangChain 能力层雏形，但 LangSmith 层还基本没有真正建立。**

---

### 12.2 LangChain：在本项目里代表什么层？

LangChain 在这个项目里，更接近：

> **节点内部能力层（capability layer）**

它解决的是“单个节点怎么做事”。

#### 典型职责

- LLM 调用
- Prompt 输入构造
- Structured output / JSON schema 输出
- Retrieval / RAG
- Tool 封装
- Context pack 组装
- LLM 节点的 retry / parse / fallback

#### 在本项目中的对应位置

较明确属于这一层的文件和模块：

- `LangGraph/src/games_news_agent/llm_provider.py`
- `LangGraph/src/games_news_agent/llm_verifier.py`
- `LangGraph/src/games_news_agent/claim_extraction.py`
- `LangGraph/src/games_news_agent/retrieval.py`
- `LangGraph/src/games_news_agent/context_packs.py`
- `LangGraph/src/games_news_agent/evidence_store.py`
- `LangGraph/src/games_news_agent/platform_writer.py`
- `LangGraph/prompts/`（未来应更系统化）

#### 当前已有

- 轻量 evidence store / retrieval 骨架
- context pack 思想
- LLM verifier harness
- provider abstraction
- 对 JSON 输出合同已有意识

#### 当前缺失

1. **统一的 LLM 节点抽象**
   - 目前各 LLM 节点能力存在，但还没统一成“输入构造 + schema 输出 + 校验 + fallback”的稳定模式。

2. **claim 级 retrieval 闭环**
   - 现在更多还是 candidate / context-pack 级；未来需要进一步收敛到 claim 级证据检索。

3. **工具层标准化**
   - `discussion_probe`、`search_expansion`、`source_navigation` 等更多还是业务模块，未来可进一步抽象成可组合能力。

4. **prompt 资产体系**
   - 还缺 prompt versioning、prompt contract、prompt 级回归测试思维。

#### 结论

本项目的 LangChain 层不是没有，而是：

> **有散件，缺体系。**

---

### 12.3 LangGraph：在本项目里代表什么层？

LangGraph 在这个项目里，代表：

> **工作流编排层 / 状态机层 / agent orchestration 层**

它解决的是“整个系统怎么跑”。

#### 典型职责

- State schema
- 节点注册
- 流程编排
- 条件路由
- 子图切分
- retry / escalation / review lane
- human-in-the-loop 入口
- story / event 生命周期管理

#### 在本项目中的对应位置

较明确属于这一层的文件和模块：

- `LangGraph/src/games_news_agent/graph.py`
- `LangGraph/src/games_news_agent/schemas.py`
- `LangGraph/src/games_news_agent/nodes.py`
- `LangGraph/src/games_news_agent/run.py`

#### 当前已有

- `StateGraph(PipelineState)` 主骨架
- 一条完整的线性主链路
- 丰富的共享状态与 artifact 持久化
- 较强的 dry-run / live-run / replay 思维

#### 当前缺失

1. **事件化中间层**
   - 缺 `EventWorkItem`
   - 缺 `RoutingDecision`
   - 缺 `ReviewQueueItem`

2. **条件路由与事件子图**
   - 目前 graph 基本还是线性边
   - 缺 official / rumor / discussion / follow-up 等 lane

3. **review-aware orchestration**
   - 缺显式的 `ready / needs_review / blocked` 路由层

4. **story / event 生命周期状态**
   - 当前主要是产物状态，还缺“状态迁移可见性”

#### 结论

本项目的 LangGraph 层：

> **基础层已经搭好，但真正的事件驱动 agent orchestration 层还没有完成。**

这也是当前最优先该补的一层。

---

### 12.4 LangSmith：在本项目里代表什么层？

LangSmith 在这个项目里，代表：

> **观测 / 调试 / 评估 / 回归比较 / 人工反馈闭环层**

它解决的是“这个系统到底跑得好不好”。

#### 典型职责

- run tracing
- node tracing
- prompt 输入输出观测
- token / latency 观测
- eval dataset
- regression comparison
- 人工反馈沉淀
- failure taxonomy

#### 在本项目中的对应位置

严格说，目前项目里还没有真正的 LangSmith 层接入；但已经存在很多“未来可接 LangSmith”的资产：

- `content_quality_report.json`
- `content_review.md`
- `human_review_template.json`
- dry-run / replay fixtures
- `collector_diagnostics.json`
- `discussion_probe_report.json`
- 各类 artifact 输出

#### 当前已有

- 质量门意识
- diagnostics artifact
- 人工评审包
- replay 思维
- 机器评分 + 人工评分共存的方向

#### 当前缺失

1. **run traceability**
   - 缺节点级 trace
   - 缺 route decision trace
   - 缺 prompt / token / latency trace

2. **dataset-driven evaluation**
   - 缺标准评测集
   - 缺 rumor / official / discussion 路由正确率评估
   - 缺节点级 evaluator

3. **regression comparison**
   - 目前更多靠人工比较 artifact，缺系统化对比机制

4. **结构化反馈闭环**
   - 人工反馈已经有，但还没形成持续积累的 failure taxonomy / golden set / eval suite

#### 结论

本项目最明显缺失的是：

> **LangSmith 层。**

不是没有评估意识，而是：

> **评估资产已经出现了，但还没有成为真正的观测与评估平台层。**

---

## 13. GamesNewsCrew 三层架构图

下面这张图把本项目按 LangChain / LangGraph / LangSmith 三层重新整理。

### 13.1 总览图

```text
┌──────────────────────────────────────────────────────────────────────┐
│                         LangSmith 层                                │
│              观测 / 调试 / 评估 / 回归 / 人工反馈闭环               │
│----------------------------------------------------------------------│
│  当前已有                                                            │
│  - content_quality_report.json                                       │
│  - content_review.md                                                 │
│  - human_review_template.json                                        │
│  - diagnostics / replay / artifacts                                  │
│                                                                      │
│  当前缺失                                                            │
│  - run tracing                                                       │
│  - route decision tracing                                            │
│  - dataset eval                                                      │
│  - regression comparison                                             │
│  - structured feedback loop                                          │
│                                                                      │
│  下一步优先级                                                        │
│  - 中高优先级：在事件子图成型后尽快补齐                              │
└──────────────────────────────────────────────────────────────────────┘
                                ▲
                                │ 评估与观测
                                │
┌──────────────────────────────────────────────────────────────────────┐
│                         LangGraph 层                                │
│                状态机 / 条件路由 / 子图 / Agent编排                 │
│----------------------------------------------------------------------│
│  当前已有                                                            │
│  - graph.py 主链路                                                   │
│  - schemas.py 共享状态                                               │
│  - nodes.py 节点集合                                                 │
│  - run.py CLI 驱动                                                   │
│  - 线性 pipeline + artifact 写出                                     │
│                                                                      │
│  当前缺失                                                            │
│  - EventWorkItem                                                     │
│  - RoutingDecision                                                   │
│  - ReviewQueueItem                                                   │
│  - 条件边 / 事件子图                                                 │
│  - review-aware routing                                              │
│  - story lifecycle state                                             │
│                                                                      │
│  下一步优先级                                                        │
│  - 最高优先级：这是当前最该补的一层                                  │
└──────────────────────────────────────────────────────────────────────┘
                                ▲
                                │ 节点内部调用能力
                                │
┌──────────────────────────────────────────────────────────────────────┐
│                         LangChain 层                                │
│               LLM / Retrieval / Tools / Prompt / Context            │
│----------------------------------------------------------------------│
│  当前已有                                                            │
│  - llm_provider / llm_verifier                                       │
│  - claim_extraction                                                  │
│  - retrieval / context_packs / evidence_store                        │
│  - platform_writer                                                   │
│  - prompt 与 JSON schema 意识                                        │
│                                                                      │
│  当前缺失                                                            │
│  - 统一 LLM node abstraction                                         │
│  - claim-level retrieval loop                                        │
│  - tool abstraction standardization                                  │
│  - prompt versioning / prompt eval                                   │
│                                                                      │
│  下一步优先级                                                        │
│  - 第二优先级：在图层清晰后继续系统化                                │
└──────────────────────────────────────────────────────────────────────┘
```

---

### 13.2 更贴近本项目文件结构的映射图

```text
GamesNewsCrew
│
├─ LangChain 层（节点内部能力层）
│  ├─ llm_provider.py
│  ├─ llm_verifier.py
│  ├─ claim_extraction.py
│  ├─ retrieval.py
│  ├─ evidence_store.py
│  ├─ context_packs.py
│  ├─ platform_writer.py
│  └─ prompts/
│
├─ LangGraph 层（工作流编排层）
│  ├─ graph.py
│  ├─ schemas.py
│  ├─ nodes.py
│  ├─ run.py
│  └─ [未来] event_work_items / routing / review queue / subgraphs
│
└─ LangSmith 层（观测评估层）
   ├─ [当前替代资产] content_quality_report.json
   ├─ [当前替代资产] content_review.md
   ├─ [当前替代资产] human_review_template.json
   ├─ [当前替代资产] diagnostics / replay fixtures
   └─ [未来] tracing / eval dataset / regression suite / feedback memory
```

---

## 14. 三层分别“当前已有 / 当前缺失 / 下一步优先级”汇总

### 14.1 LangChain 层

#### 当前已有
- LLM provider 抽象
- verifier harness
- retrieval / evidence / context pack 雏形
- 平台文案生成模块
- JSON schema / 输出合同意识

#### 当前缺失
- 统一 LLM 节点模板
- claim 级检索闭环
- prompt 资产体系
- 工具抽象标准化
- prompt 级回归测试基础

#### 下一步优先级
- **第二优先级**
- 原因：如果 LangGraph 的路由结构还没稳定，过早打磨节点内部能力会出现“节点很强，但流程不清”的问题。

---

### 14.2 LangGraph 层

#### 当前已有
- 完整主链路骨架
- 丰富共享状态
- artifact 写出与阶段化节点
- CLI 驱动与 dry-run/live-run/replay 思路

#### 当前缺失
- 事件工作单元
- 条件路由
- 事件专用子图
- review / blocked / ready lane
- 生命周期状态迁移可见性

#### 下一步优先级
- **最高优先级**
- 原因：这是项目是否真正进入“agent design phase”的决定性层。

---

### 14.3 LangSmith 层

#### 当前已有
- content quality gate
- diagnostics artifact
- 人工 review pack
- replay 夹具和结果复盘思维

#### 当前缺失
- tracing
- route explainability dashboard
- dataset eval
- regression comparison
- 持续积累的人类反馈闭环

#### 下一步优先级
- **中高优先级**
- 原因：它不是最先动手改 graph 的部分，但一旦开始做事件子图和更复杂路由，就必须尽快补齐，否则系统复杂度上升后会失控。

---

## 15. 对当前项目的最终分层判断

如果把当前 GamesNewsCrew 简化成一句结构判断：

- **LangChain 层：有能力散件，缺统一能力框架**
- **LangGraph 层：有主骨架，缺真正的事件路由编排**
- **LangSmith 层：有评估资产，缺系统化观测与回归平台**

因此，最推荐的推进顺序是：

1. **先补 LangGraph 的事件编排层**
   - `EventWorkItem`
   - `RoutingDecision`
   - `ReviewQueueItem`
   - event subgraphs
   - review-aware routing

2. **再补 LangChain 的统一节点能力层**
   - 统一 LLM node contract
   - claim-level retrieval
   - prompt contracts
   - tool abstraction

3. **随后尽快补 LangSmith 的观测评估层**
   - route trace
   - node trace
   - eval dataset
   - regression comparison
   - human feedback loop

---

## 16. 一个面向未来的判断标准

以后每次讨论“要不要加一个新层/新能力/新节点”时，可以先问：

### 如果它主要在回答这些问题，它更像 LangChain
- 模型怎么调？
- 输出怎么结构化？
- 证据怎么取？
- prompt 怎么设计？

### 如果它主要在回答这些问题，它更像 LangGraph
- 这一步之后去哪一步？
- 什么事件走哪条 lane？
- 何时 blocked？何时 review？
- 哪些节点串成一个子图？

### 如果它主要在回答这些问题，它更像 LangSmith
- 这次 run 为什么效果差？
- 哪个节点误判最多？
- 新版是否真的比旧版更好？
- 哪些样本最值得沉淀成回归集？

这个分法能帮助未来把新思路放到正确层次，避免“把编排问题写成 prompt，把评估问题写成业务规则”。
