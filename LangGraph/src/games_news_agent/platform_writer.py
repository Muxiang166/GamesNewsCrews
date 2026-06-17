"""Platform-specific copy scaffolding from ranked stories."""

from __future__ import annotations

from typing import Any


PUBLIC_LABELS_BY_STATUS = {
    "verified": ["已核实"],
    "likely": ["证据支持"],
    "credible_rumor": ["流言", "可信爆料"],
    "weak_rumor": ["流言", "待验证"],
    "unverified_rumor": ["流言", "未验证"],
    "rumor": ["流言", "未验证"],
    "conflict": ["待核查"],
    "manual_review_required": ["待核查"],
    "reject": ["不采用"],
    "unchecked": ["待核查"],
}

RUMOR_STATUSES = {"credible_rumor", "weak_rumor", "unverified_rumor", "rumor"}


def public_labels_for_status(status: str) -> list[str]:
    """Return compact user-facing labels for an internal verification status."""
    return list(PUBLIC_LABELS_BY_STATUS.get(status, ["待核查"]))


def public_label_text(status: str) -> str:
    return "".join(f"[{label}]" for label in public_labels_for_status(status))


def _shorten(text: Any, limit: int = 160) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _primary_claim(story: dict[str, Any]) -> dict[str, Any]:
    claims = story.get("claims", [])
    if isinstance(claims, list) and claims and isinstance(claims[0], dict):
        return claims[0]
    return {}


def _status_from_story(story: dict[str, Any]) -> str:
    primary = _primary_claim(story)
    status = str(primary.get("check_status", ""))
    if status:
        return status
    category = str(story.get("category", ""))
    story_status = str(story.get("status", ""))
    if category == "rumor" or story_status == "needs_review":
        return "rumor"
    if story_status == "ready":
        return "likely"
    if story_status == "rejected":
        return "reject"
    return "unchecked"


def _source_hint(source_urls: list[Any]) -> str:
    urls = [str(url) for url in source_urls if str(url).strip()]
    if not urls:
        return "来源：待补充"
    if len(urls) == 1:
        return f"来源：{urls[0]}"
    return f"来源：{urls[0]} 等 {len(urls)} 个来源"


def _asset_status(story: dict[str, Any]) -> str:
    assets = story.get("assets", [])
    if not isinstance(assets, list) or not assets:
        return "manual_fill_required"
    for asset in assets:
        if isinstance(asset, dict) and asset.get("status") == "available":
            return "available"
    return "manual_fill_required"


def _caution_for(status: str, labels: list[str]) -> str:
    if status == "credible_rumor":
        return "有待验证，请以后续官方消息或更多独立来源为准。"
    if "流言" in labels:
        return "尚未证实，请勿写成既成事实。"
    if "待核查" in labels:
        return "证据仍不足，建议只作为待核查线索。"
    return ""


def _lead_for(status: str) -> str:
    if status in RUMOR_STATUSES:
        return "爆料称"
    if status == "verified":
        return "已核实"
    if status == "likely":
        return "据现有证据"
    return "线索显示"


def _build_platform_variants(
    *,
    title: str,
    claim_text: str,
    status: str,
    labels: list[str],
    label_text: str,
    source_urls: list[Any],
    story_score: Any,
    asset_status: str,
) -> dict[str, dict[str, Any]]:
    source_hint = _source_hint(source_urls)
    caution = _caution_for(status, labels)
    lead = _lead_for(status)
    score_line = f"综合分：{story_score}" if story_score not in ("", None) else "综合分：待计算"
    asset_line = "素材：待补图" if asset_status == "manual_fill_required" else "素材：已有可用素材"
    body = _shorten(claim_text or title, 180)

    weibo_lines = [
        f"{label_text} {title}",
        f"{lead}：{body}",
        score_line,
        asset_line,
        source_hint,
    ]
    if caution:
        weibo_lines.insert(2, caution)

    xiaohongshu_lines = [
        f"{label_text} {title}",
        f"{lead}：{body}",
        f"可信度：{labels[-1] if labels else '待核查'}",
        asset_line,
        source_hint,
    ]
    if caution:
        xiaohongshu_lines.insert(2, caution)

    bilibili_lines = [
        f"{label_text}{title}",
        f"看点：{lead}，{body}",
        f"{score_line}；{asset_line}",
        source_hint,
    ]
    if caution:
        bilibili_lines.insert(2, caution)

    return {
        "weibo": {
            "platform": "weibo",
            "text": "\n".join(weibo_lines),
            "public_label_text": label_text,
            "asset_status": asset_status,
        },
        "xiaohongshu": {
            "platform": "xiaohongshu",
            "text": "\n".join(xiaohongshu_lines),
            "public_label_text": label_text,
            "asset_status": asset_status,
        },
        "bilibili": {
            "platform": "bilibili",
            "text": "\n".join(bilibili_lines),
            "public_label_text": label_text,
            "asset_status": asset_status,
        },
    }


def build_platform_posts(stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    for story in stories:
        if str(story.get("status", "")) == "rejected":
            continue
        status = _status_from_story(story)
        labels = public_labels_for_status(status)
        label_text = public_label_text(status)
        primary = _primary_claim(story)
        title = str(story.get("title") or primary.get("text") or "未命名资讯")
        source_urls = story.get("source_urls", [])
        if not isinstance(source_urls, list):
            source_urls = []
        asset_status = _asset_status(story)
        publish_status = "needs_review" if "流言" in labels or "待核查" in labels else str(story.get("status", "ready"))
        posts.append(
            {
                "story_id": str(story.get("id", "")),
                "title": title,
                "category": str(story.get("category", "")),
                "publish_status": publish_status,
                "published_at": None,
                "platform_publish_id": None,
                "story_score": story.get("story_score", ""),
                "source_urls": [str(url) for url in source_urls],
                "public_labels": labels,
                "public_label_text": label_text,
                "internal_status": status,
                "asset_status": asset_status,
                "platforms": _build_platform_variants(
                    title=title,
                    claim_text=str(primary.get("text", "")),
                    status=status,
                    labels=labels,
                    label_text=label_text,
                    source_urls=source_urls,
                    story_score=story.get("story_score", ""),
                    asset_status=asset_status,
                ),
            }
        )
    return posts
