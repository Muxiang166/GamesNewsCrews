# GamesNewsCrew 项目面试 Q&A

> 用途：为项目介绍、技术面试、系统设计问答和项目复盘准备一组可直接口述或稍作改写的回答。

---

## Q1. 向面试官介绍这个项目，目标是什么、做了什么？

### 简短版回答
这是一个面向**游戏资讯与社区热点发现**的多阶段智能体项目。目标不是简单抓“所有游戏新闻”，而是自动发现**过去 48 小时内真正值得传播的内容**，包括官方硬新闻、玩家热议、争议事件、平台价格变化、玩家趣闻和高可信流言，然后完成候选筛选、证据抓取、初步核查、故事聚合、平台文案生成和人工复核物料输出。

我一开始有一个 CrewAI 的 demo，但很快发现它更像顺序对话生成，缺少对时间窗、证据、来源和可回放 artifact 的严格控制。所以我后面把主流程迁移到了 **LangGraph**，围绕状态机来做。现在已经实现了：

- 多来源候选收集
- 48 小时时间窗口过滤
- 候选分流（main / supplemental / rejected）
- 候选记忆库（避免旧闻复读）
- 正文抓取与 evidence chunk 切分
- context pack 构建
- 规则版 claim extraction / verification scaffold
- DiscussionProbe / SearchExpansion 等检索增强
- story ranking、platform writer
- content quality gate 和人工 review pack

所以这个项目本质上不是“写几段 AI 文案”，而是在做一个**面向内容运营场景的、可审计的资讯发现与验证工作流系统**。

### 展开版回答
我会把这个项目定义成：

> 一个面向游戏资讯和社区热点的、状态驱动的内容发现与初步验证系统。

项目目标有三个层次：

1. **发现**：自动在过去 48 小时内找到值得关注的游戏事件，而不是抓一堆旧闻。
2. **判断**：区分哪些是事实新闻、哪些是热议讨论、哪些是流言、哪些只是噪声或复读。
3. **产出**：把这些结果整理成 story、简报、平台文案和人工复核包，而不是只输出一段不可解释的文字。

我实际做的工作包括：

- 从最初的顺序式 CrewAI demo，重构为 **LangGraph 状态机骨架**。
- 明确拆分数据流：`candidate -> document -> evidence -> claim -> story -> post`。
- 做了候选过滤与热度排序，把“来源权重、时效性、讨论信号、候选类型”都纳入判断。
- 设计了候选记忆库，避免旧闻或重复转载被误判成新热点。
- 做了轻量 RAG 骨架，包括正文抓取、切块、context pack。
- 对流言、讨论、官方新闻等不同类型，开始建立不同的后续处理方向。
- 最后不是直接自动发布，而是输出 `content_quality_report`、`content_review.md`、`material_bundle` 这类 artifact，让系统先进入“可复核、可迭代”的阶段。

我觉得这个项目最有价值的地方，不是单点技术，而是把**LLM、规则、状态机、人工反馈**整合成一个逐步收敛的内容工作流。

---

## Q2. 为什么一开始用 CrewAI，后来又转向 LangGraph？

### 回答
一开始用 CrewAI 是为了快速验证“多角色协作生成游戏资讯”这件事能不能跑起来，它更适合原型期。优点是上手快、角色感强、比较适合快速拼装一个 demo。

但我很快发现这个项目真正难的不是“让几个 agent 聊起来”，而是：

- 如何严格控制 48 小时时间窗
- 如何区分事实和热议
- 如何保存每一步的 artifact
- 如何让结果可回放、可调试、可复核
- 如何对候选进行分流和后续处理

这些问题本质上都更像**状态编排问题**，而不是“多角色 prompt”问题。所以我把主流程迁移到 LangGraph，让它承担：

- 状态共享
- 节点编排
- artifact 落盘
- 条件分支的未来扩展

现在我的判断是：

- **主事实链路适合 LangGraph**
- **CrewAI 更适合以后做创作型 sidecar**，比如标题角度、文案风格建议、版面 critique，而不是负责事实发现和验证。

---

## Q3. 这个项目为什么不是简单的新闻爬虫 + LLM 总结？

### 回答
因为如果只是“爬虫 + LLM 总结”，会很快遇到三个问题：

1. **旧闻污染**：抓到的大量内容不在当前时间窗内。
2. **事实与讨论混淆**：社区热议不等于事实，媒体报道也不等于热点。
3. **不可解释**：最后只给一段总结，无法知道来源、证据、筛选过程。

所以我把它拆成了几个明确层次：

- 候选发现
- 时间与来源过滤
- 候选类型分流
- 正文抓取与证据提取
- claim / story 级别组织
- 平台文案与人工评审输出

这样做好处是：

- 每一步都有 artifact
- 可以定位是 collector 差、排序差、还是 verification 差
- 后续想加 LLM、review queue、事件子图都更容易

换句话说，这个项目更像一个**内容 intelligence pipeline**，不是一个“抓网页然后让模型写总结”的脚本。

---

## Q4. 你说的“过去 48 小时”为什么这么重要？

### 回答
因为项目目标不是做百科式资讯聚合，而是做**内容运营场景下的时效性发现**。如果时间约束不硬，系统很容易抓到：

- 旧闻复盘
- 站点回顾稿
- 历史内容转载
- 长尾 SEO 内容

这样最后生成出来的东西看起来像新闻，但实际上不是“今天值得发”的内容。

所以我在候选层就把 48 小时窗口做成硬门：

- 没时间的，不进主候选
- 超窗的，直接 reject
- 旧闻后续更新才有机会作为 follow-up 保留

这样可以把很多问题在最前面低成本挡掉，而不是等到 LLM 阶段才去补救。

---

## Q5. 这个项目里的核心数据流是什么？

### 回答
我把它理解成一条逐步收敛的数据链：

```text
raw source
 -> candidate
 -> document
 -> evidence chunk
 -> context pack
 -> claim
 -> verification
 -> story
 -> platform post / review pack
```

每一层都在做不同的抽象：

- **candidate**：只是发现到的线索
- **document**：正文内容和元数据
- **evidence chunk**：可引用的证据片段
- **context pack**：压缩后的验证输入
- **claim**：可验证断言
- **story**：对外可讲述的内容单元
- **platform post**：面向平台的表达草稿

这条链的好处是：

- 数据结构清晰
- 每一层都能单独测试
- 可以区分“发现问题”和“表达问题”

---

## Q6. 这个项目的难点是什么？

### 回答
我觉得难点不是单纯的爬虫，也不是单纯的 prompt，而是**多维度同时约束**：

1. **时效性**：必须是过去 48 小时。
2. **事实性**：不能把流言写成已确认事实。
3. **热点性**：媒体有报道不代表玩家真的在讨论。
4. **可解释性**：每一步都要能复盘。
5. **成本控制**：不能什么都扔给 LLM。

尤其是“事实性”和“热点性”经常是互相拉扯的：

- 官方新闻很可信，但不一定热
- 社区热梗很热，但不一定能验证
- 流言很有传播性，但风险很高

所以系统不能只靠一个分数，要靠不同阶段分别处理。

---

## Q7. 你为什么强调 artifact 和可回放？

### 回答
因为这个项目如果没有 artifact，很难迭代。

比如某次结果差，可能原因有很多：

- collector 没抓到
- 时间解析错了
- relevance gate 太严
- discussion probe 太弱
- story ranking 抢占了名额
- LLM verification 没跑

如果每一步只保留最终文案，你根本不知道问题出在哪。

所以我让很多中间产物都落盘，比如：

- `candidates.json`
- `rejected_candidates.json`
- `documents.json`
- `evidence_chunks.json`
- `context_packs.json`
- `claims.json`
- `claim_verifications.json`
- `stories.json`
- `content_quality_report.json`
- `content_review.md`

这样我可以离线 replay，也可以逐步定位问题，这比只看最终摘要强很多。

---

## Q8. 这个项目里 LLM 放在什么位置？你为什么这么设计？

### 回答
我刻意不让 LLM 进入前置确定性环节，比如：

- RSS/网页抓取
- 时间窗过滤
- URL 范围限制
- 候选分流
- JSON artifact 写出

这些环节更适合用规则、parser 和测试去保证稳定性。

我让 LLM 进入的是高语义环节，比如：

- claim extraction
- evidence verification
- context-aware writing
- 未来的 historical context mining
- 未来的 layout planning

原因是：

1. 低层确定性问题不应该浪费 token。
2. 这些基础环节必须稳定、可复盘。
3. LLM 更适合做语义判断，而不是替代 parser。

这相当于把 LLM 当成**高层判别器和表达器**，而不是万能脚本引擎。

---

## Q9. 这个项目目前最欠缺的是什么？

### 回答
我会分三层回答：

### 1. LangGraph 层最欠缺
最欠缺的是**事件驱动路由层**。现在主图已经有了，但还偏线性 pipeline。未来应该补：

- EventWorkItem
- RoutingDecision
- ReviewQueueItem
- official / rumor / discussion 子图
- ready / needs_review / blocked 显式路由

### 2. LangChain 层最欠缺
最欠缺的是**统一的 LLM 节点抽象**，包括：

- 输入构造
- schema 输出
- parse / retry / fallback
- prompt 版本化

### 3. LangSmith 层最欠缺
最欠缺的是**观测与评估层**：

- tracing
- route correctness eval
- regression comparison
- 人工反馈沉淀

所以如果从“下一阶段最重要的事”来说，我会优先补 LangGraph 的事件编排层。

---

## Q10. 你提到 memory，这个 memory 是做什么的？

### 回答
这个 memory 不是聊天记忆，而是**候选记忆库（candidate memory store）**。

它的作用是帮助系统判断：

- 这是全新事件
- 这是 48 小时内已见过的同类事件
- 这是旧闻复读
- 这是旧事件的新进展

对应的状态大概有：

- `new_story`
- `known_recent_story`
- `follow_up_update`
- `late_repost`

这样可以减少把旧闻误当成今日热点的问题。

不过我也有意识地把它控制在“辅助 freshness 判定”这一层，而不是让 memory 过度决定内容价值。因为如果 memory 权重太大，会误杀一些真实 follow-up 事件。

---

## Q11. SearchExpansion 和 DiscussionProbe 分别是干什么的？

### 回答
这两个模块虽然都和“扩充信息”有关，但职责不一样。

### SearchExpansion
它负责：
- 基于主题缺口补搜
- 基于 event burst 做扩展搜索
- 基于现有候选做 follow-up 搜索
- 产出更多线索型候选

它更像：
> **发现层增强**

### DiscussionProbe
它负责：
- 给候选生成讨论验证入口
- 从正文和平台搜索结果中识别讨论证据
- 提升 discussion profile

它更像：
> **热点判断层增强**

简单说：
- SearchExpansion 负责“多找一点可能有价值的东西”
- DiscussionProbe 负责“判断这些东西是不是真的在被讨论”

---

## Q12. 你最近分析 `llm_search_expansion_live` 时，发现了什么问题？

### 回答
我发现“入池少”不是 memory 冲突主导，而主要是编排和配额问题。

具体来说：

1. `theme_candidate_pool` 里其实已经有不少候选，但真正被选去抓正文的数量受 `document_fetch_limit` 限制很大。
2. SearchExpansion 现在产出的大多是 supplemental / discussion lead，而不是强 main candidate。
3. discussion signal coverage 还比较低，所以很多扩展回来的线索没法在全局排序里冲到前面。
4. 全局 top-N 截断让某些板块哪怕有候选也抢不到抓取名额。

所以这个问题不是简单的“memory 与新候选冲突”，而是：

- fetch quota 太小
- lane 定位保守
- discussion support 不够强
- 排序机制对板块不够平衡

这也是为什么我后面更倾向把它往事件化和分 lane 方向重构。

---

## Q13. 为什么你现在认为项目应该走“事件驱动 agent graph”，而不是继续线性 pipeline？

### 回答
因为不同类型的内容，处理路径应该不同。

比如：
- 官方新闻适合快速事实验证
- 流言需要更严格核查，最好默认 `needs_review`
- 社区热梗应该先验证讨论热度，再决定是否写
- follow-up update 需要和历史记忆比对

如果继续一条线跑到底，会出现：

- 所有内容共用一套 verification policy
- 所有内容共用一套 ranking 逻辑
- review / blocked / ready 状态不够显式

所以更合理的方向是：

- 先生成 `EventWorkItem`
- 再根据事件类型做路由
- 不同事件走不同子图
- 最后再合并输出

这样更像真正的 agent orchestration，而不是“加了一些模块的 pipeline”。

---

## Q14. 你会怎么向面试官解释 LangChain、LangGraph、LangSmith 在这个项目里的分工？

### 回答
我会这样解释：

- **LangChain**：负责节点内部的能力，比如 LLM 调用、检索、prompt、structured output。
- **LangGraph**：负责整个系统怎么跑，比如 state、节点、分支、子图和 review lane。
- **LangSmith**：负责系统怎么被观测、调试、评估和持续改进。

在这个项目里：

- LangChain 层已经有一些雏形，但还缺统一能力抽象。
- LangGraph 层已经有主骨架，但缺事件驱动路由层。
- LangSmith 层几乎还没真正建立，但我已经有不少适合作为评估资产的 artifact。

这也是我后续规划的三层：

1. 先补 LangGraph 事件编排
2. 再补 LangChain 统一节点能力
3. 尽快补 LangSmith 的评估与回归

---

## Q15. 这个项目最能体现你的什么能力？

### 回答
我觉得它最能体现的不是单一技术点，而是**把复杂问题拆层、拆状态、拆边界**的能力。

具体包括：

1. **系统设计能力**
   - 我没有停留在“多几个 agent”这个层面，而是把系统拆成 candidate / evidence / claim / story / review 几层。

2. **工程化思维**
   - 我强调 artifact、可回放、质量门，而不是只追求最终文案效果。

3. **LLM 应用边界意识**
   - 我清楚哪些环节适合规则，哪些适合 LLM，避免把所有问题都扔给模型。

4. **迭代式架构演进能力**
   - 从 CrewAI demo 到 LangGraph 骨架，再到未来的事件驱动子图，这个过程不是推倒重来，而是逐步升级。

如果让我总结成一句话，就是：

> 我做的不是“一个会写文案的 AI demo”，而是一个正在逐步演进为可验证、可调试、可复盘的内容智能系统。

---

## Q16. 如果继续做下去，你的下一步规划是什么？

### 回答
我会按三步走：

### 第一步：补 LangGraph 事件编排层
- 新增 `EventWorkItem`
- 新增 `RoutingDecision`
- 新增 `ReviewQueueItem`
- 先实现 official / rumor / hot discussion 三条子图

### 第二步：补统一 LLM 节点能力层
- 统一 schema output
- 统一 retry / fallback
- 把 retrieval 往 claim 级推进
- 把 prompts 做成可管理资产

### 第三步：补评估与回归层
- route tracing
- golden set
- regression eval
- 人工反馈结构化沉淀

如果资源允许，后续再加创作型 sidecar，例如：
- 标题角度建议
- 社媒开场风格建议
- layout critique

但这些一定要建立在主事实链路已经稳定的基础上。

---

## Q17. 如果面试官问：这个项目目前还没有完全成熟，你怎么评价它的完成度？

### 回答
我会非常诚实地说：

它不是一个已经商业化上线的成熟系统，但已经明显超过“概念 demo”了。

我会把它定义为：

> **处于从“可运行原型”向“可演进工作流系统”过渡的阶段。**

已经完成的是：
- 主链路骨架
- 多种 artifact
- 候选筛选与记忆机制
- 轻量 evidence / verification scaffold
- content quality gate

还没完全完成的是：
- 事件级子图编排
- 更强的 discussion verification
- 更成熟的 LLM verification
- 更系统化的评估平台

但恰恰因为这些边界我都非常清楚，所以我认为这是一个**工程方向是对的，而且具备持续演进能力**的项目。

---

## Q18. 如果要一句话总结这个项目，你会怎么说？

### 回答
我会说：

> **这是一个用 LangGraph 驱动的、面向游戏资讯与社区热点发现的内容智能工作流系统，它试图把“发现、筛选、验证、写作、复核”做成一条可审计、可回放、可演进的状态链路。**
