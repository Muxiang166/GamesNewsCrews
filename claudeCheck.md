# 游戏资讯智能体 — 综合建议报告

2026年6月15日

---

## 1. 执行摘要

游戏资讯智能体拥有**设计良好的数据模型和采集基础设施**，但被**三个结构性问题**拖累：

(a) 一个 131 字段的 `TypedDict(total=False)` 抹掉了所有类型安全，每个字段都隐含 `Optional`；
(b) 一条 100% 线性的 LangGraph pipeline，完全没有用到框架的核心价值（无条件路由、无并行 fan-out、无 checkpoint、无人工中断）；
(c) LLM 集成策略构建了完善的调度基础设施（请求/响应 schema、解析函数、JSON artifact 输出），但 10 个需要的 prompt 只写了 3 个，且除了 claim verification 之外从未真正调用过 LLM。

`schemas.py` 中的 Pydantic 模型是**死文档**——`SearchCandidate`、`SourceDocument`、`Asset`、`Claim`、`Story` **定义了但从未在代码库中实例化过**。结果是：系统能确定性地采集、过滤、打包新闻，但无法执行将其与 RSS 聚合器区分开的语义判断（编辑相关性、社交热度相关性、故事聚类）。

**当前最高杠杆的单点动作**是接入 `EditorialJudgmentAgent`——`editorial_judgment.py` 中 request builder 和 response parser 已经完整实现，但没有 CLI flag、没有 prompt、没有 LLM 调用点。

---

## 2. 严重问题——按严重性排序

### 严重 1：内容质量门只是咨询性的，pipeline 忽略自己的 `blocked` 裁决

**文件：** `LangGraph/src/games_news_agent/graph.py`（第 65-70 行）

`validate_content_quality` 产出 `gate_status` 为 `"blocked"`、`"needs_review"` 或 `"pass"`。然后 graph **无条件继续**执行 `write_content_review_pack` → `write_material_bundle` → `draft_markdown` → `design_layout` → `render_assets`。**没有任何条件边。** LangGraph 的标志性特性——`graph.add_conditional_edges(...)`——从未使用。当 `gate_status == "blocked"` 时，pipeline 依然耗费算力为已经被判定为不可用的内容编写 markdown、版面和渲染队列。

**修复（低成本，高影响）：**

```python
# 在 graph.py 中，将 add_edge 替换为：
graph.add_conditional_edges(
    "validate_content_quality",
    lambda state: END if state.get("content_quality_report", {}).get("gate_status") == "blocked"
                        else "write_content_review_pack",
)
```

预估工作量：30 分钟。风险：几乎为零（纯增量改动）。

---

### 严重 2：Pydantic 模型是死代码——pipeline 数据零运行时验证

**文件：** `LangGraph/src/games_news_agent/schemas.py`（第 37-103 行）

定义了六个 Pydantic 模型。只有 `SourceConfig` 被实例化过——且立即通过 `source.model_dump(mode="json")` 转成了 dict。`PipelineState` 中的每个字段类型都是 `list[dict[str, Any]]`。后果：

- `SearchCandidate.heat_score` 声明为 `Field(ge=0.0, le=100.0)`，但 `ranking.py:232` 在裸 dict 上设置 `enriched["heat_score"] = heat_score`——**约束从未在运行时执行**。
- 模型中改一个字段名，会导致 54 个源文件中约 150 处 `.get()` 调用静默返回 `""`。
- `verify_claims` 用 `claim_verifications` **覆盖了 `claims`**（nodes.py 第 1104 行）：两个完全不同的 shape 共享一个 `list[dict[str, Any]]` 类型。下游节点在此之后读取 `claims` 实际拿到的是 verifications——任何工具都无法检测。

**修复（中等工作量，渐进式）：** 从使用一个模型开始。让 `build_evidence_chunks` 返回 `list[EvidenceChunk]`（匹配 `evidence_store.py:47-63` 中稳定 shape 的新 Pydantic 模型）。在 state 边界用 `.model_dump()` 转存。在读取侧用 `EvidenceChunk.model_validate(item)` 校验。这样得到的是进 state 的已验证 dict 和出 state 的已验证模型——无需改变 TypedDict 类型。然后推进到 `fetch_documents` → `context_packs` → `claims`。

---

### 严重 3：没有 LLM 模型选择——每次调用使用相同的 DeepSeek 配置

**文件：** `LangGraph/src/games_news_agent/llm_provider.py`（第 18-26、28-58 行）

`LlmConfig` 只读取一个 `DEEPSEEK_MODEL` 环境变量。没有按任务选择模型的能力。"廉价模型铺广度、强模型做收口"的设计原则**只是愿景**。代码对 claim verification（需要推理）、query compression（需要速度）和 relevance classification（需要批量）使用相同的 `temperature=0.1`、`max_tokens=700` 和模型。

**修复（低成本）：** 给 `load_llm_config` 加 `task_type` 参数：

```python
def load_llm_config(task_type: str = "default", env: Mapping[str, str] | None = None) -> LlmConfig:
    # default = 廉价/快速；"reasoning" = 强模型/慢
    model_map = {
        "default": ("deepseek-chat", 0.0, 400),
        "reasoning": ("deepseek-reasoner", 0.2, 1200),
    }
```

---

### 严重 4：`editorial_judgment.py` 完整但无执行路径

**文件：** `LangGraph/src/games_news_agent/editorial_judgment.py`（272 行）

request builder（`build_editorial_judgment_requests`）、response parser（`parse_editorial_judgment_result`）、output schema、risk flags 和安全约束全部已实现，质量达到生产级别。输出 `editorial_judgment_requests.json` 作为 artifact 写入磁盘。但是：

- **没有 CLI flag：** `run_llm_editorial_judgment` 在代码库中不存在（已 grep 确认）。
- **没有 prompt：** `LangGraph/prompts/editorial_judgment.md` 不存在（10 个需要的 prompt 只有 3 个存在）。
- **没有 LLM 调用点：** 没有任何地方用 editorial judgment requests 调用 `run_llm_json_requests`。
- **结果从未被应用：** requests 写入磁盘后被遗弃——没有节点读回来调整 story 分数。

这是**#1 质量瓶颈**。最新一次 run 中，`platform_business`、`auction` 和 `personal_sentiment` 内容稳定压过 `core_game_update` 内容。对候选标题做一次二分类 LLM 调用就能立即修复。成本：约 200 tokens/候选 × 40 候选/run ≈ 8K tokens。这是**最高 ROI 的可用改动**。

---

### 严重 5：多个节点覆盖同一个 JSON 文件——调试噩梦

`context_packs.json` 被 `fetch_documents`（nodes.py 约第 510 行）写入，然后被 `deduplicate_stories`（第 1034 行）覆盖，再被 `probe_discussions`（第 970 行）覆盖。`candidates.json` 被 `search_candidates` 写入后被 `probe_discussions`（第 972 行）重新写入。**磁盘上的文件不代表任何单一节点的输出**——它代表最后运行的节点。如果 pipeline 在 `probe_discussions` 和 `extract_assets` 之间崩溃，磁盘上的 `context_packs.json` 包含探针增强过的数据，但 `extract_assets` 从 state 读取（可能是探针前的数据）。不一致。

**修复（中等工作量）：** 采用每个 artifact 写入一次的策略。每个节点写入唯一命名的文件（`03_fetch_documents_context_packs.json`、`06_probe_discussions_context_packs.json`）。最后一步"发布"将规范版本复制到固定名称。或者通过一个强制 write-once 的 `ArtifactStore` 类集中管理所有 artifact I/O。

---

### 严重 6：HTTP 抓取零重试、零退避、无限速

**文件：** `LangGraph/src/games_news_agent/fetching.py`（第 84-121 行）

`HttpFetcher.fetch_text()` 只做一次 `urlopen()` 调用。一次 429 或瞬时 DNS 故障就杀死整个来源。没有重试、没有指数退避、没有 `Retry-After` 头解析、没有按域名限速。`collect_from_sources` 零延迟连续发出请求。IGN、GameSpot 和 Gamersky 各有 5 页以上的分页——对单个域名连续发出 15-20 个快速请求。这**在第一个繁忙新闻日一定会**触发 Cloudflare/WAF 限流。

**修复（低成本）：** 在 `HttpFetcher.fetch_text()` 内添加 3 次重试 + 指数退避（1s、2s、4s）。在 collector 循环中添加 `per_domain_cooldown_ms` 参数。两项合计约 30 行代码。

---

### 严重 7：`PipelineState` 是 131 字段的无结构 blob——TypedDict 提供零安全

**文件：** `LangGraph/src/games_news_agent/schemas.py`（第 106-237 行）

因为 `total=False`，每个字段都隐含 `Optional[list[dict[str, Any]]]`。类型检查器将 `state.get("candidates")` 视为 `list[dict[str, Any]] | None`——`list[dict[str, Any]]` 部分抹掉了所有结构。有 50+ 个 `_path` 字段，仅因为节点同时向 state 和磁盘写数据。`notes` 列表是伪装成 state 的非结构化日志。

**修复（中等工作量，分阶段）：** 阶段 A：拆分为按阶段组织的 TypedDict，组合成 `PipelineState`（运行时成本：零）。阶段 B：用 Pydantic 模型替换 4 个最稳定的 `list[dict[str, Any]]` 字段（至少：`EvidenceChunk`、`ContextPack`、`ClaimVerification`、`SearchCandidate`）。阶段 C：引入 `manifest.json` 注册表替代 50+ 个 `_path` 字段。

---

## 3. 技能架构

当前 18 节点的线性 pipeline 应演化为 **11 个独立可调用的 skill**，通过 JSON artifact 文件通信。这正是 roadmap 中"Workflow-first with bounded ReAct"愿景描述但尚未实现的架构。

### 技能目录

| # | 技能 | 模型层级 | 输入 | 输出 | 优先级 | 可独立 |
|---|------|---------|------|------|--------|--------|
| 1 | **collect-game-news** | 无 LLM | sources.yaml、lookback_hours、memory_path | candidates.json、source_health.json、collector_diagnostics.json | P0 | ✅ |
| 2 | **fetch-and-chunk-documents** | 无 LLM | theme_candidate_pool.json | documents.json、evidence_chunks.json、context_packs.json | P0 | ✅ |
| 3 | **verify-claims** | STRONG | claims.json、evidence_chunks.json、context_packs.json | claim_verifications.json | P1 | ✅ |
| 4 | **rank-and-select-stories** | STRONG（判断） | claim_verifications.json、context_packs.json、theme_candidate_pool.json | stories.json、theme_sections.json | P1 | ✅ |
| 5 | **probe-social-heat** | CHEAP | context_packs.json、candidates.json | social_heat_observations.json、增强后的 context_packs | P2 | ✅ |
| 6 | **quality-gate** | 无 LLM（评分）+ STRONG（反思） | 所有 artifact | content_quality_report.json | P2 | ✅ |
| 7 | **generate-platform-posts** | CHEAP（当前为模板） | stories.json、assets.json | platform_posts.json | P3 | ✅ |
| 8 | **generate-briefing** | CHEAP（当前为模板） | stories.json、所有 artifact | briefing.md | P3 | ✅ |
| 9 | **bundle-materials** | 无 LLM | stories.json、platform_posts.json、assets.json | material_bundle.json | P3 | ✅ |
| 10 | **expand-search-coverage** | CHEAP | source_theme_counts.json、candidates.json | expansion_candidates.json | P4 | ✅ |
| 11 | **plan-selection-backfill** | 无 LLM | selection_stage_diagnostics.json、theme_candidate_pool.json | backfill_candidates.json | P4 | ✅ |

### 技能合约模板

每个 skill 实现以下接口：

```python
class SkillInput(BaseModel):
    """必需输入 artifact 的路径"""
    # verify-claims 示例：
    claims_path: str
    evidence_chunks_path: str
    context_packs_path: str
    run_llm: bool = False
    llm_limit: int = 10
    output_dir: str

class SkillOutput(BaseModel):
    """产出 artifact 的路径 + 统计"""
    claim_verifications_path: str
    llm_verification_requests_path: str | None
    llm_status: str
    stats: dict[str, int]  # {total、verified、likely、rumor、conflict、reject}
```

Skills **从不修改共享状态**——只从文件读、向文件写。编排器传递文件路径，不传递内存状态。

### 模型分层策略

| 层级 | 任务 | 配置 |
|------|------|------|
| **无 LLM** | 采集、抓取、切块、素材提取、打包、回填规划 | 不适用 |
| **CHEAP** | Query 压缩、相关性分类（同事件？同游戏？48h内？）、编辑判断（二元：游戏/非游戏）、语言检测、模板化写作 | `deepseek-chat`、temperature=0.0、max_tokens=400 |
| **STRONG** | Claim 验证（证据评估、流言可信度、信源可信度加权）、故事聚类/去冲突、质量失败反思 | `deepseek-reasoner` 或 `deepseek-chat`、temperature=0.2、max_tokens=1200 |

### 技能图（替代线性 graph）

```
collect-game-news ──┬──> expand-search-coverage [可选]
                    │
                    └──> probe-social-heat [可选，与 expand 并行]
                         │
                         ▼
                    fetch-and-chunk-documents
                         │
                         ▼
                    verify-claims [STRONG]
                         │
                         ▼
                    rank-and-select-stories [STRONG 用于判断]
                         │
               ┌─────────┼─────────┐
               ▼         ▼         ▼
         generate-   generate-   bundle-
         briefing    platform-   materials
                     posts
               │         │         │
               └─────────┼─────────┘
                         ▼
                    quality-gate ──> [人工复核] ──> END 或循环返回
```

---

## 4. 近期改进（未来 2-4 周）

### 你提出的顺序 vs 建议调整

**你提出的顺序：**
1. ThemeSectionCarryover
2. CoreGameStoryPolicy / ThemeReranker v1
3. ImportantRejectedCandidatesDiagnostics + EventWindowContext
4. CandidateDedup v1 / StoryClusterer v1

**判断：部分正确，但缺少最高 ROI 的一项。** 第 2 和第 4 项位置正确。第 1 和第 3 项是**输出诊断**——告诉你出了什么问题，但不修复任何东西。应该在所有项之前插入一项：

### 建议的近期顺序：

#### 第 1 周：EditorialJudgmentAgent（插入到最前面——不在你的列表中但是最高 ROI）

这是**唯一的最高 ROI 改动**。request builder 和 response parser 已实现。只需要三件事：

1. **创建 `LangGraph/prompts/editorial_judgment.md`**——一个 prompt，要求 LLM 将每个候选分类为 `core_game_news`、`platform_or_pc_game_adjacent`、`community_game_meme` 或 `off_topic`，并给出可发布性判断。包含 2-3 个 few-shot 示例，展示中文游戏新闻标题的正确与错误分类。

2. **添加 `--run-llm-editorial-judgment` CLI flag** 到 `main.py` 并作为 `run_llm_editorial_judgment: bool` 传入 `PipelineState`。

3. **接入 LLM 调用** 在 `nodes.py` 的 `score_heat` 中：在 `build_editorial_judgment_requests` 之后，若 `run_llm_editorial_judgment`，则调用 `run_llm_json_requests` 并应用结果：`reject` 可发布性则从 `theme_sections` 中移除；`core_game_news` 获得分数加成；`off_topic` 进入拒绝池。

**成本：约 8K tokens/run。工作量：约 4 小时。**

#### 第 1-2 周：CoreGameStoryPolicy / ThemeReranker v1（你的第 2 项——保留）

优先级正确。上一步的 editorial judgment 结果直接输入 reranker：被分类为 `core_game_news` 的 story 获得分数乘数；`off_topic` 和 `platform_business` 获得分数惩罚。reranker 应使用 LLM 判断在每个主题板块内重新排序，确保 `core_game_update` 故事稳定排在 `platform_business` 和 `personal_sentiment` 之上。

具体实现：
- 在 `story_ranking.py`（或新的 `theme_reranker.py`）中：基于 `candidate_type` 和 LLM `game_relevance` 判断应用每板块乘数。
- `core_game_news` → 乘数 1.3
- `platform_or_pc_game_adjacent` → 乘数 0.9
- `community_game_meme` → 乘数 0.8（保留，但排在硬新闻之后）
- `off_topic` → 乘数 0.0（排除）
- 添加每板块软上限：每个主题板块最终最多 5 条 story。

#### 第 2 周：ThemeSectionCarryover（你的第 1 项——移到这里）

诊断问题"为什么板块 X、Y、Z 在繁忙新闻日有零条 story"很重要，但应先修复导致问题的排序策略（上面的第 2 项），再添加诊断来验证修复是否有效。Carryover 逻辑应：
- 读取 `selection_stage_diagnostics.json`。
- 对最终 story < 2 但池内候选 > 5 的板块：输出结构化警告。
- 对最终 story < 2 且池内候选 < 5 的板块：标记为"采集缺口"（不是排序问题）。

#### 第 2-3 周：ImportantRejectedCandidatesDiagnostics + EventWindowContext（你的第 3 项——保留）

这是人工审核者的体验改进。关键输出是 `content_review.md` 中按热度分数列出前 5 条被拒候选及拒绝原因的部分，让审核者能发现假阴性。EventWindowContext 是数据模型补充：为候选标注同一 48h 窗口内的相邻事件，帮助审核者理解上下文（如"这条任天堂直面会报道与另外 3 条直面会报道同时出现"）。

#### 第 3-4 周：CandidateDedup v1 / StoryClusterer v1（你的第 4 项——保留）

当前 `nodes.py` 中的 `deduplicate_stories` 是一个空操作透传。真正的去重需要：
1. **URL 规范化：** 去除查询参数、统一 `http`/`https`、规范化尾部斜杠。
2. **标题相似度：** 在每个主题板块内对规范化标题使用 Levenshtein 或 Jaccard 距离。
3. **语义去冲突：** 对模糊配对（同游戏不同事件 vs 同事件不同来源），写入 `dedup_semantic_review_requests.json` 供 LLM 审核（schema 已存在）。
4. **合并 vs 丢弃：** 重复转载被丢弃；带新细节的后续报道作为 `follow_up_updates` 合并到原始 story。

**重要：** 不要在运行 LLM editorial judgment 之前运行 LLM 去重——你会对垃圾去重。正确顺序必须是：editorial judgment（过滤非游戏）→ 去重（在游戏内容内合并重复）。

---

## 5. 中期改进（1-3 个月）

### 5.1 将 `PipelineState` 拆分为可组合的阶段 TypedDict

```python
class CollectionStageState(TypedDict, total=False):
    sources: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    supplemental_candidates: list[dict[str, Any]]
    rejected_candidates: list[dict[str, Any]]
    source_health_path: str
    # ... 仅采集相关字段

class EvidenceStageState(TypedDict, total=False):
    documents: list[dict[str, Any]]
    document_errors: list[dict[str, Any]]
    evidence_chunks: list[dict[str, Any]]
    context_packs: list[dict[str, Any]]

class PipelineState(CollectionStageState, EvidenceStageState, ..., total=False):
    topic: str
    dry_run: bool
    # ... 仅真正的全局字段
```

运行时零成本（TypedDict 会被擦除），但能让 mypy/pyright 标记跨阶段字段访问。

### 5.2 合并琐碎节点；使用 LangGraph Send 实现并行

应合并到调用方的节点：
- `extract_assets`（15 行，一个函数调用）→ 合并到 `fetch_documents`
- `design_layout`（桩）→ 合并到未来的 `package_outputs`
- `render_assets`（桩）→ 合并到未来的 `package_outputs`
- `write_material_bundle` 和 `write_content_review_pack` → 合并到 `quality-gate` skill

应并行运行的节点（通过 LangGraph `Send`）：
- `expand_search_candidates` || `probe_discussions`（都从 `theme_candidate_pool` 读取，互相独立）
- `extract_claims` || `deduplicate_stories`（都从 `context_packs` 读取，互相独立）

### 5.3 通过 ArtifactManifest 消除 `_path` 字段

用一个 `ArtifactManifest` 替代 50+ 个 `_path` 字段：

```python
class ArtifactManifest(BaseModel):
    artifacts: dict[str, str] = {}  # artifact_name → output_dir 内的相对路径
```

节点调用 `manifest.register("candidates", output_dir / "candidates.json")` 而不是将 `candidates_path` 返回到 state 中。下游节点从 manifest 解析路径。

### 5.4 实现 LlmRouter——按任务选择模型

```python
class LlmRouter:
    TIERS = {
        "cheap": LlmConfig(model="deepseek-chat", temperature=0.0, max_tokens=400),
        "reasoning": LlmConfig(model="deepseek-reasoner", temperature=0.2, max_tokens=1200),
    }

    @classmethod
    def for_task(cls, task: str) -> LlmConfig:
        if task in {"verify_claims", "editorial_judgment", "story_clustering"}:
            return cls.TIERS["reasoning"]
        return cls.TIERS["cheap"]
```

所有 LLM 调用点传递 `task_type` 给 `load_llm_config(task_type=task_type)`。

### 5.5 补充 7 个缺失的 prompt（含 few-shot 示例和思维链）

新 prompt 的优先级：

| # | Prompt 文件 | 任务 | 紧急程度 |
|---|-----------|------|---------|
| 1 | `editorial_judgment.md` | 游戏相关性 + 可发布性判断 | **立即**——#1 质量瓶颈 |
| 2 | `semantic_relevance.md` | 这个社交媒体结果是否关于同一游戏/事件？ | 高——当前 35/40 结果 `off_topic` |
| 3 | `claim_extractor.md` | 从 context pack 中提取原子 claim（而非每篇文章一个） | 高——当前"一个 context_pack 一个 claim"的粒度是错误的 |
| 4 | `story_clusterer.md` | 两条 story 是同一事件还是不同事件？ | 中——阻塞 CandidateDedup v1 |
| 5 | `markdown_editor.md` | 从 story card 生成叙事性简报 | 低——模板当前够用 |
| 6 | `platform_writer.md` | 以平台特定风格改写故事 | 低——模板当前够用 |
| 7 | `historical_context_miner.md` | 寻找历史先例 | 低——Phase 7 功能 |

每个 prompt 必须包含：(a) 2-3 个正确 vs 错误输出的 few-shot 示例；(b) 验证/推理类 prompt 的思维链结构；(c) 匹配代码约束的显式字符/token 限制。

### 5.6 将 `nodes.py` 拆分为 `nodes/` 包

```
src/games_news_agent/nodes/
    __init__.py              # 重导出
    _base.py                 # _output_dir、_append_note、_load_json_artifact
    plan_sources.py          # ~30 行
    search_candidates.py     # ~240 行（已足够独立成文件）
    expand_search.py         # ~80 行
    fetch_documents.py       # ~80 行
    probe_discussions.py     # ~140 行
    extract_assets.py        # ~15 行（理想情况下合并到 fetch_documents）
    deduplicate_stories.py   # ~20 行（会随 CandidateDedup v1 增长）
    extract_claims.py        # ~30 行
    verify_claims.py         # ~50 行
    score_heat.py            # ~100 行
    plan_backfill.py         # ~30 行
    write_posts.py           # ~30 行
    validate_quality.py      # ~50 行
    write_review.py          # ~40 行
    write_bundle.py          # ~30 行
    draft_markdown.py        # ~40 行
    design_layout.py         # ~20 行
    render_assets.py         # ~20 行
```

**工作量：2 小时。风险：低（纯重构，无行为变更）。**

### 5.7 给 HttpFetcher 添加重试/退避

```python
def fetch_text(self, url: str, ..., max_retries: int = 3) -> FetchResult:
    for attempt in range(max_retries):
        try:
            with self.open_url(request, timeout=self.timeout) as response:
                if response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(retry_after)
                    continue
                ...
        except (OSError, URLError) as exc:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return FetchResult(status="error", ...)
```

### 5.8 添加全 pipeline 集成测试

- `tests/test_graph.py`：验证 `build_graph()` 的节点集、边、入口点。
- `tests/test_integration_pipeline.py`：dry-run 全 graph，断言所有预期 artifact 文件存在、所有 notes 存在。
- `tests/test_regression.py`：基于 harness 的 golden-file 对比，对标 `tests/fixtures/expected/`。
- `tests/test_editorial_judgment_e2e.py`：patch HTTP 层，验证 request building → 假 LLM 响应 → parsing → 分数应用。

---

## 6. 长期愿景（3-12 个月）

### 6.1 Skill 编排器替代线性 graph

一个轻量 DAG 编排器（可保留 LangGraph，但使用合适的条件边、并行 Send 和 checkpoint），调用第 3 节中定义的 11 个 skill。Skills 可独立调度（每小时采集一次、每天验证一次、每天简报一次）。Skills 通过 artifact 文件通信，而非共享内存状态。

### 6.2 SQLite 支撑的 evidence store 和 memory

用 SQLite 替换 JSON 文件 memory。优势：原子写入、并发读取访问、跨 run 可查询（"显示过去 30 天关于 Switch 2 的所有已验证 claim"）、用 Alembic 管理 schema 迁移。

### 6.3 Playwright 浏览器 sidecar——用于 JS 渲染源

新增 `BrowserFetcher`，实现与 `HttpFetcher` 相同的 `fetch_text(url) -> FetchResult` 接口。使用 Playwright 同步 API。通过 `collector == "browser_listing"` 控制。在 `sources.yaml` 的 `collector_config` 中添加 `wait_for_selector`、`scroll_count`、`scroll_delay_ms`。**不要**将 Playwright 设为硬依赖——使用可选导入。

### 6.4 评估用的真实标注数据集

收集 30-60 天的 pipeline 输出。人工标注 200-500 条 story：正确的游戏相关性、正确的流言状态、正确的排序顺序。将此数据集用于：
- 排序变更的 NDCG/MRR 评估。
- Editorial judgment 的精确率/召回率。
- Prompt 版本的 A/B 测试。
- 对标 golden output 的回归测试。

### 6.5 结构化日志、指标和 LangSmith 追踪

用 `logging`（结构化 JSON 格式）替换 `print()` 调用。为每个节点添加 `@track` 装饰器，记录墙钟时间、内存使用、候选数量。集成 LangSmith 进行 LLM 调用的分布式追踪。

### 6.6 内容审核 Web UI

一个简单的本地 web 应用：
- 以渲染 HTML 形式展示 `content_review.md`。
- 允许审核者批准/拒绝/编辑 story。
- 提供 run 之间的 diff 视图。
- 作为人工介入的接口。

### 6.7 多语言内容对齐

实体规范化："Nintendo Switch 2"、"Switch 2"、"NS2"、"任天堂 Switch 2" 映射到同一规范实体。跨语言去重："这篇 IGN 文章和这篇游民星空文章是关于同一事件的"。为简报提供翻译层（中文/英文）。

---

## 7. 路线图缺失的内容

现有的 1223 行 roadmap（`docs/roadmap.md`）在功能上非常详尽，但有七个显著缺口：

### 7.1 无运维/部署模型

Roadmap 描述了系统应该做什么，但没有描述应该如何运行。缺失：调度策略（cron？systemd timer？Kubernetes CronJob？）、artifact 保留策略、容器化（Dockerfile）、`.env` 之外的密钥管理、健康检查端点、成本追踪仪表板。

### 7.2 无增量运行支持

每次 run 都重新采集、重新过滤、重新验证所有内容。对于每 6 小时运行一次、面向"过去 48 小时"的系统，这意味着约 75% 的已采集内容被重复处理。Roadmap 从未解决如何跳过已处理的候选、如何将新候选合并到现有候选池、或如何用新故事更新已有简报。

### 7.3 无冷启动策略

系统首次部署时，`candidate_memory.json` 为空，evidence store 无历史数据，`HistoricalContextMiner` 无可查内容。Roadmap 没有解决从零历史数据引导的问题——而这正是每个新用户的初始状态。

### 7.4 无内容交付机制

Pipeline 产出 `briefing.md`、`platform_posts.json` 和图片。没有任何交付这些产物的机制：没有 email、没有 Slack/Discord webhook、没有 RSS feed 输出、没有 API 端点。用户必须手动导航到输出目录。

### 7.5 无评估/基准测试框架

Roadmap 提到"收集 30-60 天候选数据进行离线评估"（第 930-932 行），但没有定义：计算什么指标（NDCG、MRR、精确率/召回率）、如何标注数据、如何 A/B 测试 prompt 版本、或如何独立执行 Phase 4.5 的退出标准（目前是 pipeline 给自己的作业打分）。

### 7.6 Phase 4.5 退出标准是自指的

Roadmap 设定了硬性门禁（`overall_score >= 80`，第 738 行），但这些分数由生产内容的同一条 pipeline 计算。没有独立验证。系统可以轻易地通过在评分上放水来通过自己的质量门。Roadmap 需要一个带人工标注真实标签的外部评估 harness。

### 7.7 无伦理/安全考量

Roadmap 正确地坚持流言标注，但没有解决：(a) 放大关于真实公司/产品/个人的未验证流言的伦理影响；(b) 某些流言话题的"不放大"列表；(c) 爬取 Bilibili/微博/Reddit 时遵守平台服务条款；(d) 重新发布带图片的游戏新闻时的版权/合理使用考量。

---

## 8. 对你具体问题的回答

### 问：应该在哪里创建 skills？

**答：** 创建 `LangGraph/src/games_news_agent/skills/` 包。每个 skill 是一个单独的 Python 文件，实现第 3 节定义的 `SkillInput → SkillOutput` 合约。Skills 从 `output_dir/` 中的 JSON 文件读取，向 `output_dir/` 中的 JSON 文件写入，返回带 artifact 路径和统计信息的 `SkillOutput`。11 个 skill 及其边界在第 3 节中定义。

**第一个要提取的 skill 不是 `collect-game-news`**（最复杂的，跨多个模块约 500 行）。从 **`quality-gate`** 开始——最简单（读 artifact、产出报告）、无 LLM 依赖、是自然的人工介入决策点。首先提取它可以以最小风险验证 skill 合约模式。然后提取 `generate-briefing`（纯输出、无 mutation）。然后 `probe-social-heat`。最后才处理 `collect-game-news`。

### 问：如何用廉价模型铺广度 + 强模型做收口？

**答：** 实现一个 `LlmRouter` 类，按任务选择模型（见第 5.4 节）。路由表：

```
CHEAP  (deepseek-chat, temp=0.0, max_tokens=400):
  - Query 压缩
  - 搜索结果相关性分类（同事件？同游戏？48h内？）
  - 编辑判断（二元：游戏/非游戏分类）
  - 语言检测

STRONG (deepseek-reasoner, temp=0.2, max_tokens=1200):
  - Claim 验证（证据评估、流言可信度、矛盾解决）
  - 故事聚类 / 去冲突
  - 质量门反思（为什么分数低、该改什么）
```

**不要引入 asyncio。** 代码库是同步的。使用 `ThreadPoolHttpFetcher`（通过现有 `open_url` 注入点实现线程池并发）处理 discussion probe 和 search expansion 节点中的并行 HTTP 抓取。这是零架构变更的即插即用替换。

### 问：另一个模型的建议如何比较？

这个问题似乎引用了分析材料中未包含的外部 AI 建议。没有该建议的具体文本，我无法做直接比较。然而，本报告中包含的审计识别了任何称职的架构审查都会发现的相同核心问题：

- `PipelineState` TypedDict 是最大的 bug 来源。
- `editorial_judgment.md` prompt + LLM 执行路径是最高 ROI 的缺失功能。
- 线性 LangGraph graph 未充分利用框架。
- RSS 应用 `feedparser` 替代 `xml.etree.ElementTree`。
- "一个 context_pack 一个 claim"的粒度是错误的。

如果另一个模型的建议与以上任何一点矛盾，那它可能低估了 editorial judgment 作为质量瓶颈的重要性，或高估了基础设施工作（asyncio、框架迁移）相对于 prompt 工程和分类质量的价值。

---

## 最终总结：如果未来两周只做三件事

1. **接入 `EditorialJudgmentAgent`**——创建 prompt、添加 CLI flag、调用 LLM、将结果应用到 story 分数。这修复你的 #1 质量问题。
2. **从 `validate_content_quality` 添加 `conditional_edges`**——当质量门说 `blocked` 时停止 pipeline 继续产出 markdown/版面/渲染队列。30 分钟改动。
3. **给 `HttpFetcher` 添加重试/退避**——3 次重试 + 指数退避、解析 `Retry-After` 头。这防止你的第一个繁忙新闻日变成静默失败。
