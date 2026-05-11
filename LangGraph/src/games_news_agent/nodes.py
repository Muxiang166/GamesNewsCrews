"""LangGraph node implementations.

The current nodes are intentionally conservative stubs. They establish state
shape, output contracts, and file artifacts before live collectors are wired in.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .ranking import filter_and_rank_candidates
from .schemas import PipelineState
from .source_catalog import load_sources


def _append_note(state: PipelineState, note: str) -> list[str]:
    return [*state.get("notes", []), note]


def _output_dir(state: PipelineState) -> Path:
    output_dir = Path(state.get("output_dir", "outputs/langgraph/latest"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def plan_sources(state: PipelineState) -> dict[str, Any]:
    sources = load_sources()
    return {
        "sources": [source.model_dump(mode="json") for source in sources],
        "notes": _append_note(state, f"Loaded {len(sources)} configured sources."),
    }


def _run_now(state: PipelineState) -> datetime:
    raw = state.get("started_at")
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _sources_by_id(state: PipelineState) -> dict[str, dict[str, Any]]:
    return {str(source["id"]): source for source in state.get("sources", [])}


def _dry_run_candidates(now: datetime) -> list[dict[str, Any]]:
    examples = [
        {
            "title": "示例线索：微软游戏爆笑梗图在社区刷屏",
            "url": "https://example.invalid/microsoft-game-meme",
            "source_id": "xiaoheihe",
            "snippet": "示例：玩家围绕某微软游戏的离谱 BUG 制作梗图，评论和转发快速升高。",
            "query": "微软 游戏 梗图 热门",
            "observed_at": (now - timedelta(hours=2)).isoformat(),
            "heat_signals": {"likes": 5200, "comments": 980, "shares": 1300},
            "tags": ["meme", "player_story", "hot_discussion"],
        },
        {
            "title": "示例线索：索尼 DEI 与亏损相关说法待核查",
            "url": "https://example.invalid/sony-dei-loss-rumor",
            "source_id": "weibo",
            "snippet": "示例：社区将索尼业务亏损与 DEI 争议关联传播，需要区分事实与因果推断。",
            "query": "索尼 DEI 亏损 游戏",
            "observed_at": (now - timedelta(hours=5)).isoformat(),
            "heat_signals": {"likes": 2300, "comments": 1600, "reposts": 760},
            "tags": ["controversy", "dei", "loss", "hot_discussion"],
        },
        {
            "title": "示例线索：Nintendo Switch 2 与初代涨价讨论升温",
            "url": "https://example.invalid/switch-price-increase",
            "source_id": "gamergen",
            "snippet": "示例：多平台讨论 Switch 2 与初代配件/游戏价格上涨，需要核对官方售价和地区差异。",
            "query": "Switch 2 Switch 涨价",
            "observed_at": (now - timedelta(hours=7)).isoformat(),
            "heat_signals": {"likes": 1200, "comments": 340, "shares": 120},
            "tags": ["price", "market", "hot_discussion"],
        },
        {
            "title": "示例线索：玩家无厘头操作聊天截图被大量转载",
            "url": "https://example.invalid/player-chat-screenshot",
            "source_id": "bilibili",
            "snippet": "示例：玩家在游戏内做出反常操作后留下聊天截图，被二创视频和动态大量转发。",
            "query": "游戏 玩家 聊天截图 离谱 操作",
            "observed_at": (now - timedelta(hours=1)).isoformat(),
            "heat_signals": {"views": 180000, "likes": 9000, "comments": 1800, "danmaku": 900},
            "tags": ["player_story", "meme", "hot_discussion"],
        },
        {
            "title": "示例旧线索：Nintendo Switch 2 发布复盘",
            "url": "https://example.invalid/old-switch-2-recap",
            "source_id": "ign",
            "snippet": "示例：旧硬件发布复盘，应被 48 小时时间窗口过滤。",
            "query": "Nintendo Switch 2 recap",
            "observed_at": (now - timedelta(hours=96)).isoformat(),
            "heat_signals": {"likes": 50, "comments": 3},
            "tags": ["official_news"],
        },
    ]

    discovered_at = now.isoformat()
    for item in examples:
        item["discovered_at"] = discovered_at
    return examples


def search_candidates(state: PipelineState) -> dict[str, Any]:
    if state.get("dry_run", True):
        now = _run_now(state)
        raw_candidates = _dry_run_candidates(now)
        candidates, rejected = filter_and_rank_candidates(
            raw_candidates,
            _sources_by_id(state),
            now=now,
            lookback_hours=int(state.get("lookback_hours", 48)),
        )
        return {
            "candidates": candidates,
            "rejected_candidates": rejected,
            "notes": _append_note(
                state,
                (
                    "Dry run: generated example high-heat game/community leads "
                    "and applied the configured time window."
                ),
            ),
        }

    raise NotImplementedError("Live search collectors are not implemented yet.")


def fetch_documents(state: PipelineState) -> dict[str, Any]:
    return {
        "documents": [],
        "notes": _append_note(state, "No documents fetched in the skeleton run."),
    }


def extract_assets(state: PipelineState) -> dict[str, Any]:
    return {
        "assets": [],
        "notes": _append_note(state, "No assets extracted in the skeleton run."),
    }


def deduplicate_stories(state: PipelineState) -> dict[str, Any]:
    return {
        "stories": [],
        "notes": _append_note(state, "No story clusters produced in the skeleton run."),
    }


def extract_claims(state: PipelineState) -> dict[str, Any]:
    return {
        "stories": state.get("stories", []),
        "notes": _append_note(state, "Claim extraction is waiting for live stories."),
    }


def verify_claims(state: PipelineState) -> dict[str, Any]:
    return {
        "stories": state.get("stories", []),
        "notes": _append_note(state, "Verification is waiting for extracted claims."),
    }


def score_heat(state: PipelineState) -> dict[str, Any]:
    return {
        "stories": state.get("stories", []),
        "notes": _append_note(state, "Heat scoring is waiting for candidates."),
    }


def draft_markdown(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    briefing_path = output_dir / "briefing.md"
    now = datetime.now(timezone.utc).isoformat()
    topic = state.get("topic", "games")
    lookback_hours = state.get("lookback_hours", 48)
    candidates = state.get("candidates", [])
    rejected = state.get("rejected_candidates", [])

    if candidates:
        candidate_lines = [
            f"- {item['title']} | heat={item.get('heat_score', 0)} | reasons={', '.join(item.get('heat_reasons', []))}"
            for item in candidates
        ]
    else:
        candidate_lines = ["- 暂无候选。"]

    content = "\n".join(
        [
            "# 48小时游戏资讯简报",
            "",
            f"- Topic: {topic}",
            f"- Lookback hours: {lookback_hours}",
            f"- Generated at: {now}",
            "",
            "当前是 LangGraph dry-run，尚未接入真实搜索和抓取；以下为用于验证流程的示例线索，不可发布。",
            "",
            "## 时间窗口内高热候选",
            "",
            *candidate_lines,
            "",
            f"过滤掉的线索数：{len(rejected)}",
            "",
            "## 待接入模块",
            "",
            "- 固定来源采集",
            "- 48 小时时间过滤",
            "- 热度评分",
            "- Claim 拆解与证据验证",
            "- 素材抽取",
            "- 平台图文排版",
        ]
    )
    briefing_path.write_text(content, encoding="utf-8")

    return {
        "briefing_path": str(briefing_path),
        "notes": _append_note(state, f"Wrote skeleton briefing to {briefing_path}."),
    }


def design_layout(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    manifest_path = output_dir / "layout_manifest.json"
    manifest = {
        "version": "0.1.0",
        "status": "skeleton",
        "canvases": [
            {
                "platform": "xiaohongshu",
                "size": {"width": 1242, "height": 1660},
                "slides": [],
            },
            {
                "platform": "weibo",
                "size": {"width": 1080, "height": 1920},
                "slides": [],
            },
            {
                "platform": "bilibili",
                "size": {"width": 1920, "height": 1080},
                "slides": [],
            },
        ],
        "missing_assets": [],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "layout_manifest_path": str(manifest_path),
        "notes": _append_note(state, f"Wrote layout manifest to {manifest_path}."),
    }


def render_assets(state: PipelineState) -> dict[str, Any]:
    output_dir = _output_dir(state)
    render_queue_path = output_dir / "render_queue.json"
    queue = {
        "status": "skeleton",
        "renderer": "html_css_playwright_planned",
        "items": [],
        "layout_manifest_path": state.get("layout_manifest_path"),
    }
    render_queue_path.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "render_queue_path": str(render_queue_path),
        "notes": _append_note(state, f"Wrote render queue to {render_queue_path}."),
    }
