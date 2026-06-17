# 采集后选择与回填策略

本文记录 `social_heat_relevance_live` 暴露出的一个关键问题：爬取侧已经能找到大量候选，但进入最终 story 的数量仍然很少。根因不在爬虫，而在采集后的预算分配、取证、粗排、精排和回填边界。

## 本轮诊断结论

基于 `outputs/langgraph/social_heat_relevance_live/`：

- `candidates.json`：206 条主候选。
- `supplemental_candidates.json`：239 条补充候选。
- `theme_candidate_pool.json`：五个板块各自最多 20 条，任天堂板块 `candidate_count=34`、`pool_count=20`。
- `context_packs.json`：旧实现只有 20 条，因为当时 `--document-fetch-limit 20` 仍是全局预算。
- `theme_candidate_pool.sections[].fetch_selected_count`：旧实现每个板块约 4 条。
- `story_candidates.json`：14 条，其中任天堂 3 条。
- `theme_sections.json`：任天堂最终入选 3 条。

所以“任天堂相关新闻很多但入选少”的主要断点是：

```text
34 条任天堂候选
 -> 20 条进入主题候选池
 -> 旧实现只有 4 条被 document_fetch_limit 选中抓正文
 -> 3 条生成可发布 story
 -> 3 条入选最终 briefing
```

当前的“如果板块不够，则按排名顺序填充”只发生在 `story_candidates` 之后。它不能回到 `theme_candidate_pool` 把未抓正文的候选补进来，因此看起来像候选“早就被筛选掉了”。

## 当前采集后流程

```text
search_candidates
 -> candidates / supplemental_candidates / rejected_candidates
 -> expand_search_candidates
 -> fetch_documents
    -> build_thematic_candidate_selection
    -> _select_document_fetch_candidates
    -> documents / evidence_chunks / context_packs
 -> probe_discussions
 -> extract_claims
 -> verify_claims
 -> score_heat
    -> build_ranked_stories
    -> build_thematic_story_selection
 -> content_review
```

现在有两层选择：

- 候选池粗排：`build_thematic_candidate_selection`，每板块最多 20 条。
- 正文取证预算：`_select_document_fetch_candidates`，当前已改为先按五个板块拆分，再把 `document_fetch_limit` 作为每板块预算使用。

后续 story 精排只能处理已经有正文、claim 和 verification 的候选。

2026-06-14 修正：`--document-fetch-limit 20` 现在表示每个板块最多抓 20 条正文；五个板块都有候选时，首轮最多约 100 条进入正文取证。`ThemeFetchBackfill` 不再是常规补救，而是当某板块首轮候选、正文抓取或 story 转化仍不足时才触发的保险机制。

## 需要新增的阶段

### 1. StageSelectionDiagnostics

目标：每轮都写出候选在各阶段掉了多少，避免只看最终 `stories.json`。

建议产物：

- `selection_stage_diagnostics.json`
- `selection_stage_diagnostics.md`

核心字段：

```json
{
  "sections": {
    "nintendo": {
      "candidate_count": 34,
      "pool_count": 20,
      "fetch_selected_count": 4,
      "context_pack_count": 4,
      "claim_count": 4,
      "story_candidate_count": 3,
      "final_selected_count": 3,
      "dropped_before_fetch": 16,
      "drop_reason": "document_fetch_budget"
    }
  }
}
```

### 2. ThemeFetchBackfill

目标：当某个板块 `story_candidate_count` 低于目标值时，从该板块 `theme_candidate_pool` 未 fetch 的候选里按排名继续补抓正文。

建议第一版规则：

- `min_story_candidates_per_section=5`
- `max_backfill_fetch_per_section=8`
- `max_total_backfill_fetch=20`
- 只补 `candidate_lane=main`。
- 优先补 `candidate_type in {"news", "rumor", "platform_price", "hardware_platform", "review_score"}`。
- 暂不补明显 supplemental、泛娱乐、攻略、折扣、图集。

第一版可作为第二轮取证节点：

```text
score_heat_precheck
 -> section shortage detected
 -> backfill_fetch_documents
 -> append documents/evidence/context_packs
 -> extract_claims / verify_claims / score_heat rerun
```

### 3. CoreGameNewsEditorialPolicy

当前排序不能只追逐讨论度。`NS2 吃灰`、个人感悟、泛平台情绪和花边争议可以作为补充板块或单条热议，但不能反复覆盖“游戏本体相关”的新作公布、发售日、试玩版、DLC、更新、实机演示、预告片、评分解禁和核心玩法细节。

建议后续在 `candidate -> claim -> story` 链路里新增或细化编辑意图：

- `core_game_announcement`：新作、续作、重制、移植、正式公布。
- `game_detail_update`：玩法细节、发售日、试玩、DLC、补丁、实机、预告片。
- `platform_business`：主机、订阅、涨价、硬件、平台策略。
- `community_sentiment`：玩家讨论、争议、吐槽。
- `meme_or_player_story`：梗图、无厘头操作、聊天截图、玩家故事。
- `personal_opinion_repeat`：重复性个人感悟、泛泛讨论、低信息密度热议。

第一版排序策略：

- 各主题板块至少保留一定比例的 `core_game_announcement` / `game_detail_update`。
- `community_sentiment` 和 `personal_opinion_repeat` 只能在同一主题中保留少量代表，重复话题聚合为一条 story 的补充说明。
- 社交热度只作为放大器，不作为唯一入选理由；没有同事件证据或只有泛泛讨论时，热度分应封顶。
- `ThemeFetchBackfill` 在板块不足时优先回填游戏本体资讯类型，而不是继续回填重复情绪型内容。
- LLM/人工语义核查后续负责判断模糊标题是否真属于“游戏本体新信息”，但事实证据仍来自正文和来源链接。

### 4. LongLookbackEvaluationHarness

目标：收集 1-2 个月候选作为测试数据，专门测试采集后的阶段，而不是每次依赖 48 小时 live run。

建议不要直接把 1-2 个月数据用于日常 briefing，而是作为离线评估集：

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 720 --topic games --document-fetch-limit 20 --theme-candidate-pool-limit 300 --output-dir outputs\langgraph\eval_30d_collection --memory-path outputs\langgraph\memory\eval_30d_candidate_memory.json
```

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 1440 --topic games --document-fetch-limit 30 --theme-candidate-pool-limit 500 --output-dir outputs\langgraph\eval_60d_collection --memory-path outputs\langgraph\memory\eval_60d_candidate_memory.json
```

评估目的：

- 统计每个板块从候选到 story 的转化率。
- 检查夏日游戏节、直面会、发布会等爆发日是否被正确识别。
- 检查旧闻、重复新闻、晚发复述和当天更新是否被正确区分。
- 为未来 Agent 的 retry policy 提供经验样本。

## 是否引入已有 skills / 工具链

可以，但应分层使用：

- LangGraph workflow：继续负责主流程编排和 artifact 落盘。
- LangChain：适合作为局部 provider/LLM wrapper，例如 query compression、metadata extraction、date normalization。
- LLM/RAG：适合处理同事件判断、标题去修饰、同名游戏消歧、旧闻/后续更新判断。
- Agent：适合在某阶段指标低于阈值时选择工具，例如“任天堂 story 不足，是否补抓更多任天堂候选、换搜索词、查官方源、或请求人工导入”。

不建议：

- 用 Agent 直接替代整个 pipeline。
- 让 LLM 直接决定哪些 URL 是事实证据。
- 用 1-2 个月数据训练日常 48 小时排序权重，而不区分测试集和生产运行。

## Agent Retry 经验规则

未来 `SelectionRecoveryAgent` 可以读取 `selection_stage_diagnostics.json`，按下面顺序行动：

1. 如果 `candidate_count` 足够但 `fetch_selected_count` 低，执行 `ThemeFetchBackfill`。
2. 如果 `candidate_count` 不足，执行 `SearchExpansion` 或 `SourceRecovery`。
3. 如果 `fetch_selected_count` 足够但 `story_candidate_count` 低，检查正文抓取、claim extraction 和 verification。
4. 如果 `story_candidate_count` 足够但 `final_selected_count` 低，检查 story ranking、主题均衡、单源上限和热度证据。
5. 如果 social heat 证据低，先 query compression，再 provider 切换，不直接让 LLM 改事实。
