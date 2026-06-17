"""Story building and ranking from verified claims."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .story_sections import SECTION_IDS, classify_story_section


PUBLISHABLE_STATUSES = {"verified", "likely", "credible_rumor", "weak_rumor", "rumor"}
RUMOR_STATUSES = {"credible_rumor", "weak_rumor", "unverified_rumor", "rumor"}
STATUS_BONUS = {
    "verified": 20.0,
    "likely": 12.0,
    "credible_rumor": 7.0,
    "weak_rumor": 1.0,
    "rumor": 2.0,
}
PREFERRED_PATTERNS = {
    "meme_or_funny": ("爆笑", "离谱", "无厘头", "梗", "整活", "逆天"),
    "player_story": ("玩家", "客服", "补偿", "聊天", "截图", "操作"),
    "market_or_hardware": ("涨价", "价格", "售价", "硬件", "手柄", "主机", "switch", "xbox", "ps5", "pc"),
    "new_feature": ("新功能", "上线", "更新", "新增", "在线数据", "多主机"),
    "authority_or_accurate_rumor": ("权威", "官方", "确认", "定档", "爆料"),
    "controversy": ("争议", "dei", "亏损", "索尼", "微软", "任天堂"),
    "review_score": ("m站", "metacritic", "opencritic", "媒体评分", "评分", "高分", "低分", "斩获"),
}
LOW_FIT_PATTERNS = ("采访", "玩法细节", "机制", "新消息", "抉择机制", "情感玩法", "实机演示")


def _story_id(claim: dict[str, Any]) -> str:
    return str(claim.get("story_id") or claim.get("metadata", {}).get("candidate_url") or claim.get("text", ""))


def _heat_score(claim: dict[str, Any]) -> float:
    metadata = claim.get("metadata", {})
    if isinstance(metadata, dict):
        value = metadata.get("heat_score", 0)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _discussion_profile(claim: dict[str, Any]) -> dict[str, Any]:
    metadata = claim.get("metadata", {})
    if not isinstance(metadata, dict):
        return {}
    profile = metadata.get("discussion_profile", {})
    if isinstance(profile, dict):
        return profile
    return {}


def _raw_discussion_score(claim: dict[str, Any]) -> float:
    metadata = claim.get("metadata", {})
    if isinstance(metadata, dict):
        value = metadata.get("discussion_score")
        if isinstance(value, (int, float)):
            return float(value)
    profile = _discussion_profile(claim)
    value = profile.get("score", 0)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _discussion_score(claim: dict[str, Any]) -> float:
    profile = _discussion_profile(claim)
    score = _raw_discussion_score(claim)
    if not profile:
        return score

    level = str(profile.get("level", "none"))
    if profile.get("has_discussion_evidence") or profile.get("has_direct_engagement"):
        return score
    if level in {"discussed", "trending"}:
        return score
    if level == "weak":
        return min(score, 8.0)
    return 0.0


def _best_discussion_profile(claims: list[dict[str, Any]]) -> dict[str, Any]:
    best_claim = max(claims, key=_discussion_score, default={})
    return _discussion_profile(best_claim)


def _category(claim_type: str, status: str) -> str:
    if status in RUMOR_STATUSES or claim_type == "rumor":
        return "rumor"
    if claim_type == "platform_price":
        return "market"
    if claim_type == "hardware_platform":
        return "hardware_platform"
    if claim_type == "review_score":
        return "review_score"
    return "news"


def _editorial_label(status: str) -> str:
    labels = {
        "verified": "可作为已验证事实使用",
        "likely": "证据支持，发布时保留来源",
        "credible_rumor": "可信爆料，有待验证",
        "weak_rumor": "弱流言，有待验证",
        "rumor": "流言，有待验证",
    }
    return labels.get(status, "待复核")


def _source_urls(claims: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for claim in claims:
        for url in claim.get("source_urls", []):
            value = str(url)
            if value and value not in urls:
                urls.append(value)
    return urls


def _claim_source_id(claim: dict[str, Any]) -> str:
    metadata = claim.get("metadata", {})
    if isinstance(metadata, dict):
        return str(metadata.get("source_id", "")).lower()
    return ""


def _claim_urls(claim: dict[str, Any]) -> list[str]:
    return [str(url) for url in claim.get("source_urls", []) if str(url).strip()]


def _is_chinese_source(claim: dict[str, Any]) -> bool:
    source_id = _claim_source_id(claim)
    urls = " ".join(_claim_urls(claim)).lower()
    if source_id in {"gamersky", "gamergen", "bilibili", "weibo", "xiaoheihe", "tieba"}:
        return True
    return any(
        domain in urls
        for domain in (
            "gamersky.com",
            "bilibili.com",
            "weibo.com",
            "3dmgame.com",
            "ali213.net",
        )
    )


def _is_ign_source(claim: dict[str, Any]) -> bool:
    source_id = _claim_source_id(claim)
    urls = " ".join(_claim_urls(claim)).lower()
    return source_id == "ign" or "ign.com" in urls


def _primary_claim(claims: list[dict[str, Any]]) -> dict[str, Any]:
    for claim in claims:
        if _is_chinese_source(claim):
            return claim
    return claims[0] if claims else {}


def _source_urls_with_primary(claims: list[dict[str, Any]], primary: dict[str, Any]) -> list[str]:
    ordered = [primary, *[claim for claim in claims if claim is not primary]]
    return _source_urls(ordered)


def _primary_metadata(primary: dict[str, Any]) -> dict[str, Any]:
    metadata = primary.get("metadata", {})
    if isinstance(metadata, dict):
        return metadata
    return {}


def _claim_metadatas(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metadatas: list[dict[str, Any]] = []
    for claim in claims:
        metadata = claim.get("metadata", {})
        if isinstance(metadata, dict):
            metadatas.append(metadata)
    return metadatas


def _first_metadata_value(claims: list[dict[str, Any]], *keys: str) -> Any:
    for metadata in _claim_metadatas(claims):
        for key in keys:
            value = metadata.get(key)
            if isinstance(value, str):
                if value.strip():
                    return value
            elif value not in (None, "", []):
                return value
    return ""


def _metadata_list(claims: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for metadata in _claim_metadatas(claims):
        raw = metadata.get(key)
        candidates = raw if isinstance(raw, list) else [raw]
        for item in candidates:
            value = str(item or "").strip()
            if value and value not in values:
                values.append(value)
    return values


def _theme_section_from_metadata(claims: list[dict[str, Any]]) -> str:
    direct = str(_first_metadata_value(claims, "theme_section") or "").strip()
    if direct in SECTION_IDS:
        return direct
    for key in ("theme_section_candidates", "source_entry_themes"):
        for value in _metadata_list(claims, key):
            if value in SECTION_IDS:
                return value
    fallback = str(_first_metadata_value(claims, "source_entry_theme", "source_section_theme") or "").strip()
    return fallback if fallback in SECTION_IDS else ""


def _theme_section_candidates(claims: list[dict[str, Any]], theme_section: str) -> list[str]:
    values = _metadata_list(claims, "theme_section_candidates")
    for value in _metadata_list(claims, "source_entry_themes"):
        if value in SECTION_IDS and value not in values:
            values.append(value)
    if theme_section in SECTION_IDS and theme_section not in values:
        values.insert(0, theme_section)
    return values


def _metadata_editorial_priority(metadata: dict[str, Any]) -> int:
    value = metadata.get("editorial_priority")
    if isinstance(value, (int, float)):
        return int(value)
    return -1


def _editorial_focus_from_metadata(claims: list[dict[str, Any]]) -> tuple[str, int]:
    best_intent = ""
    best_priority = -1
    for metadata in _claim_metadatas(claims):
        intent = str(metadata.get("editorial_intent") or "").strip()
        priority = _metadata_editorial_priority(metadata)
        if intent and priority > best_priority:
            best_intent = intent
            best_priority = priority
    if best_priority < 0:
        return "", 0
    return best_intent, best_priority


def _primary_url(primary: dict[str, Any], source_urls: list[str]) -> str:
    metadata = _primary_metadata(primary)
    candidate_url = str(metadata.get("candidate_url") or "").strip()
    if candidate_url:
        return candidate_url
    return source_urls[0] if source_urls else ""


def _primary_candidate_type(primary: dict[str, Any], claim_type: str) -> str:
    metadata = _primary_metadata(primary)
    return str(metadata.get("candidate_type") or claim_type)


def _source_language(primary: dict[str, Any]) -> str:
    return "zh" if _is_chinese_source(primary) else "en"


def _source_preference(primary: dict[str, Any], claims: list[dict[str, Any]]) -> str:
    has_ign = any(_is_ign_source(claim) for claim in claims)
    if _is_chinese_source(primary) and has_ign:
        return "chinese_source_preferred_ign_context_available"
    if _is_chinese_source(primary):
        return "chinese_source_preferred"
    if _is_ign_source(primary):
        return "english_ign_fallback"
    return "original_source_used"


def _story_score(claims: list[dict[str, Any]]) -> float:
    best_heat = max((_heat_score(claim) for claim in claims), default=0.0)
    best_discussion = max((_discussion_score(claim) for claim in claims), default=0.0)
    best_confidence = max(
        (float(claim.get("confidence", 0)) for claim in claims if isinstance(claim.get("confidence", 0), (int, float))),
        default=0.0,
    )
    best_status_bonus = max(
        (STATUS_BONUS.get(str(claim.get("check_status", "")), 0.0) for claim in claims),
        default=0.0,
    )
    source_count = len(_source_urls(claims))
    editorial_fit = max((_editorial_fit_score(claim) for claim in claims), default=0.0)
    return round(
        min(
            100.0,
            best_heat * 0.55
            + best_discussion * 0.25
            + best_confidence * 16.0
            + best_status_bonus
            + source_count * 2.0
            + editorial_fit,
        ),
        2,
    )


def _editorial_fit_score(claim: dict[str, Any]) -> float:
    text = " ".join(
        [
            str(claim.get("text", "")),
            str(claim.get("claim_type", "")),
            " ".join(str(reason) for reason in claim.get("verification_reasons", [])),
        ]
    ).lower()
    score = 0.0
    for patterns in PREFERRED_PATTERNS.values():
        if any(pattern.lower() in text for pattern in patterns):
            score += 4.0
    if any(pattern.lower() in text for pattern in LOW_FIT_PATTERNS):
        score -= 7.0
    return max(-10.0, min(20.0, score))


def build_ranked_stories(
    claim_verifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claim_verifications:
        status = str(claim.get("check_status", ""))
        if status not in PUBLISHABLE_STATUSES:
            continue
        grouped[_story_id(claim)].append(dict(claim))

    stories: list[dict[str, Any]] = []
    for story_id, claims in grouped.items():
        primary = _primary_claim(claims)
        status = str(primary.get("check_status", ""))
        claim_type = str(primary.get("claim_type", ""))
        category = _category(claim_type, status)
        story_status = "needs_review" if category == "rumor" else "ready"
        editorial_fit = max((_editorial_fit_score(claim) for claim in claims), default=0.0)
        discussion_score = max((_discussion_score(claim) for claim in claims), default=0.0)
        discussion_profile = _best_discussion_profile(claims)
        source_urls = _source_urls_with_primary(claims, primary)
        story_score = _story_score(claims)
        primary_metadata = _primary_metadata(primary)
        theme_section = _theme_section_from_metadata(claims)
        theme_candidates = _theme_section_candidates(claims, theme_section)
        editorial_intent, editorial_priority = _editorial_focus_from_metadata(claims)
        stories.append(
            {
                "id": story_id,
                "title": str(primary.get("text", "未命名资讯")),
                "url": _primary_url(primary, source_urls),
                "source_id": str(primary_metadata.get("source_id") or ""),
                "candidate_type": _primary_candidate_type(primary, claim_type),
                "candidate_lane": str(primary_metadata.get("candidate_lane") or ""),
                "theme_section": theme_section,
                "theme_section_candidates": theme_candidates,
                "source_entry_theme": str(_first_metadata_value(claims, "source_entry_theme") or ""),
                "source_entry_themes": _metadata_list(claims, "source_entry_themes"),
                "source_section_theme": str(_first_metadata_value(claims, "source_section_theme") or ""),
                "editorial_intent": editorial_intent,
                "story_editorial_intent": editorial_intent,
                "editorial_priority": editorial_priority,
                "category": category,
                "status": story_status,
                "editorial_label": _editorial_label(status),
                "editorial_fit_score": editorial_fit,
                "score": story_score,
                "story_score": story_score,
                "heat_score": max((_heat_score(claim) for claim in claims), default=0.0),
                "discussion_score": round(discussion_score, 2),
                "discussion_level": discussion_profile.get("level", "none"),
                "discussion_profile": discussion_profile,
                "source_urls": source_urls,
                "source_language": _source_language(primary),
                "source_preference": _source_preference(primary, claims),
                "claims": claims,
                "publish_status": "unpublished",
                "published_at": None,
                "platform_publish_id": None,
            }
        )
        stories[-1]["theme_section"] = classify_story_section(stories[-1])

    stories.sort(key=lambda item: item.get("story_score", 0), reverse=True)
    return stories
