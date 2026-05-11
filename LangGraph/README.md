# Games News Agent - LangGraph Skeleton

这是多智能体游戏资讯智能体的新核心骨架。当前版本只搭好 LangGraph 状态机、数据结构、来源配置和空跑输出，不进行真实联网抓取。

目标流程：

```text
plan_sources
 -> search_candidates
 -> fetch_documents
 -> extract_assets
 -> deduplicate_stories
 -> extract_claims
 -> verify_claims
 -> score_heat
 -> draft_markdown
 -> design_layout
 -> render_assets
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

输出默认写入：

- `outputs/langgraph/latest/briefing.md`
- `outputs/langgraph/latest/layout_manifest.json`
- `outputs/langgraph/latest/render_queue.json`

下一步要接入真实采集器：搜索 API、固定游戏门户、社区热帖、素材抽取和 48 小时过滤。
