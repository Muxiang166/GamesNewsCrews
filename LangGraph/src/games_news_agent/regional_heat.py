"""Regional discussion-platform routing for heat validation.

The module only builds auditable probe targets. It does not scrape platforms,
call an LLM, or treat discussion as factual verification.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus


REGIONAL_HEAT_PLATFORMS: dict[str, tuple[str, ...]] = {
    "zh_cn": ("bilibili", "weibo", "tieba", "xiaoheihe"),
    "en_global": ("reddit", "youtube", "steam", "x"),
    "ja_jp": ("x_japan", "youtube", "nicovideo", "5ch"),
    "global": ("bilibili", "weibo", "reddit", "steam"),
}

SOURCE_REGION_HINTS: dict[str, str] = {
    "gamergen": "zh_cn",
    "gamersky": "zh_cn",
    "bilibili": "zh_cn",
    "weibo": "zh_cn",
    "tieba": "zh_cn",
    "xiaoheihe": "zh_cn",
    "ign": "en_global",
    "pc_gamer": "en_global",
    "gamespot": "en_global",
    "xbox_wire": "en_global",
    "playstation_blog": "en_global",
    "nintendo": "en_global",
    "famitsu": "ja_jp",
    "4gamer": "ja_jp",
    "dengekionline": "ja_jp",
}

LANGUAGE_REGION_HINTS: dict[str, str] = {
    "zh": "zh_cn",
    "zh-cn": "zh_cn",
    "cn": "zh_cn",
    "en": "en_global",
    "en-us": "en_global",
    "en-gb": "en_global",
    "ja": "ja_jp",
    "jp": "ja_jp",
    "ja-jp": "ja_jp",
}


def infer_heat_region(candidate: dict[str, Any]) -> str:
    """Infer the discussion region used to validate heat for a candidate."""

    language = str(candidate.get("source_language") or candidate.get("language") or "").strip().lower()
    if language in LANGUAGE_REGION_HINTS:
        return LANGUAGE_REGION_HINTS[language]

    source_id = str(candidate.get("source_id") or "").strip().lower()
    if source_id in SOURCE_REGION_HINTS:
        return SOURCE_REGION_HINTS[source_id]

    url = str(candidate.get("url") or "").lower()
    if any(domain in url for domain in ("gamersky.com", "bilibili.com", "weibo.com", "baidu.com")):
        return "zh_cn"
    if any(domain in url for domain in ("ign.com", "gamespot.com", "pcgamer.com", "xbox.com", "playstation.com")):
        return "en_global"
    if any(domain in url for domain in ("famitsu.com", "4gamer.net", "dengekionline.com")):
        return "ja_jp"
    return "global"


def search_target(platform: str, query: str) -> dict[str, Any]:
    """Build a public or manual search target for a regional platform."""

    encoded = quote_plus(query)
    access = "public_search_page"
    if platform == "bilibili":
        url = f"https://search.bilibili.com/all?keyword={encoded}"
    elif platform == "weibo":
        url = f"https://s.weibo.com/weibo?q={encoded}"
    elif platform == "reddit":
        url = f"https://www.reddit.com/search/?q={encoded}&sort=new"
    elif platform == "steam":
        url = f"https://steamcommunity.com/search/?q={encoded}"
    elif platform == "tieba":
        url = f"https://tieba.baidu.com/f/search/res?ie=utf-8&qw={encoded}"
    elif platform == "youtube":
        url = f"https://www.youtube.com/results?search_query={encoded}"
    elif platform == "x":
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"
        access = "manual_or_api_required"
    elif platform == "x_japan":
        url = f"https://x.com/search?q={encoded}%20lang%3Aja&src=typed_query&f=live"
        access = "manual_or_api_required"
    elif platform == "nicovideo":
        url = f"https://www.nicovideo.jp/search/{encoded}"
    elif platform == "5ch":
        url = f"https://find.5ch.net/search?q={encoded}"
        access = "manual_or_api_required"
    elif platform == "xiaoheihe":
        url = ""
        access = "manual_app_probe_required"
    else:
        url = ""
        access = "manual_or_api_required"
    return {
        "platform": platform,
        "query": query,
        "url": url,
        "access": access,
    }


def build_regional_heat_targets(
    candidate: dict[str, Any],
    query: str,
    *,
    platforms: tuple[str, ...] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Return the inferred heat region and search targets for the candidate."""

    region = infer_heat_region(candidate)
    selected_platforms = platforms if platforms is not None else REGIONAL_HEAT_PLATFORMS.get(region, REGIONAL_HEAT_PLATFORMS["global"])
    return region, [search_target(platform, query) for platform in selected_platforms]
