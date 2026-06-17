"""Source dominance diagnostics.

The audit explains why one source dominates candidates or selected stories. It
does not change ranking; downstream nodes may choose to use its recommendations
after human or LLM review.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


HEAT_WORDS = (
    "热议",
    "玩家",
    "全网",
    "爆火",
    "爆笑",
    "争议",
    "刷屏",
    "讨论",
    "评论",
    "trending",
    "viral",
    "debate",
    "discussion",
)

NOISE_TYPES = {
    "deal",
    "guide",
    "general_tech",
    "meme_gallery",
    "shopping",
    "entertainment",
}


def _candidate_url(candidate: dict[str, Any]) -> str:
    return str(candidate.get("url") or candidate.get("candidate_url") or "").strip()


def _source_id(item: dict[str, Any]) -> str:
    return str(item.get("source_id") or "unknown").strip() or "unknown"


def _ratio(value: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(value / total, 4)


def _has_title_heat(candidate: dict[str, Any]) -> bool:
    title = str(candidate.get("title") or "").lower()
    return any(word.lower() in title for word in HEAT_WORDS)


def _is_noise(candidate: dict[str, Any]) -> bool:
    candidate_type = str(candidate.get("candidate_type") or candidate.get("type") or "").lower()
    lane = str(candidate.get("candidate_lane") or "").lower()
    theme = str(candidate.get("theme_section") or "").lower()
    return candidate_type in NOISE_TYPES or lane == "supplemental" or theme == "supplemental"


def _observation_has_real_engagement(observation: dict[str, Any]) -> bool:
    if str(observation.get("status") or "") != "ok":
        return False
    if str(observation.get("heat_validity_hint") or "") == "game_discussion":
        return True
    signals = observation.get("engagement_signals", {})
    if isinstance(signals, dict):
        for key in ("comments", "reposts", "shares", "danmaku", "replies", "posts"):
            value = signals.get(key, 0)
            if isinstance(value, (int, float)) and value > 0:
                return True
    return False


def _candidate_source_by_url(candidates: list[dict[str, Any]]) -> dict[str, str]:
    return {
        _candidate_url(candidate): _source_id(candidate)
        for candidate in candidates
        if _candidate_url(candidate)
    }


def _source_names(state: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for source in state.get("sources", []):
        if isinstance(source, dict):
            source_id = str(source.get("id") or "").strip()
            if source_id:
                names[source_id] = str(source.get("name") or source_id)
    return names


def _source_stats(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates = [item for item in state.get("candidates", []) if isinstance(item, dict)]
    supplemental = [item for item in state.get("supplemental_candidates", []) if isinstance(item, dict)]
    if not candidates and not supplemental:
        candidates = _fallback_candidates_from_ranked_artifacts(state)
    all_candidates = [*candidates, *supplemental]
    candidate_source = _candidate_source_by_url(all_candidates)
    names = _source_names(state)

    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "source_id": "unknown",
            "source_name": "unknown",
            "candidate_count": 0,
            "main_candidate_count": 0,
            "supplemental_candidate_count": 0,
            "document_count": 0,
            "title_heat_word_count": 0,
            "real_engagement_count": 0,
            "noise_candidate_count": 0,
            "reasons": [],
            "metrics": {},
        }
    )

    for candidate in candidates:
        source_id = _source_id(candidate)
        item = stats[source_id]
        item["source_id"] = source_id
        item["source_name"] = names.get(source_id, source_id)
        item["candidate_count"] += 1
        item["main_candidate_count"] += 1
        if _has_title_heat(candidate):
            item["title_heat_word_count"] += 1
        if _is_noise(candidate):
            item["noise_candidate_count"] += 1

    for candidate in supplemental:
        source_id = _source_id(candidate)
        item = stats[source_id]
        item["source_id"] = source_id
        item["source_name"] = names.get(source_id, source_id)
        item["candidate_count"] += 1
        item["supplemental_candidate_count"] += 1
        if _has_title_heat(candidate):
            item["title_heat_word_count"] += 1
        if _is_noise(candidate):
            item["noise_candidate_count"] += 1

    for document in [item for item in state.get("documents", []) if isinstance(item, dict)]:
        source_id = _source_id(document)
        if source_id == "unknown":
            source_id = candidate_source.get(str(document.get("candidate_url") or ""), "unknown")
        item = stats[source_id]
        item["source_id"] = source_id
        item["source_name"] = names.get(source_id, source_id)
        item["document_count"] += 1

    for observation in [item for item in state.get("social_heat_observations", []) if isinstance(item, dict)]:
        source_id = candidate_source.get(str(observation.get("candidate_url") or ""), "unknown")
        item = stats[source_id]
        item["source_id"] = source_id
        item["source_name"] = names.get(source_id, source_id)
        if _observation_has_real_engagement(observation):
            item["real_engagement_count"] += 1

    return dict(stats)


def _fallback_candidates_from_ranked_artifacts(state: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in state.get("story_candidates", []):
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "title": item.get("title", ""),
                "url": _first_url(item),
                "source_id": item.get("source_id") or item.get("primary_source_id") or "unknown",
                "candidate_type": item.get("claim_type") or item.get("category") or "",
                "theme_section": item.get("theme_section") or "",
            }
        )
    if candidates:
        return candidates
    for item in state.get("claim_verifications", []):
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        candidates.append(
            {
                "title": item.get("text", ""),
                "url": _first_url(item),
                "source_id": metadata.get("source_id") or item.get("source_id") or "unknown",
                "candidate_type": item.get("claim_type") or "",
                "theme_section": metadata.get("theme_section") or "",
            }
        )
    return candidates


def _first_url(item: dict[str, Any]) -> str:
    urls = item.get("source_urls")
    if isinstance(urls, list) and urls:
        return str(urls[0])
    return str(item.get("url") or item.get("candidate_url") or "")


def build_source_dominance_audit(state: dict[str, Any]) -> dict[str, Any]:
    """Explain source dominance from existing pipeline artifacts."""

    stats = _source_stats(state)
    total_candidates = sum(int(item["candidate_count"]) for item in stats.values())
    if not stats or total_candidates <= 0:
        return {
            "version": "1.0.0",
            "summary": "No candidates available for source dominance audit.",
            "dominant_source_id": "",
            "dominant_source_share": 0.0,
            "sources": {},
            "risk_flags": ["no_candidates"],
            "recommended_actions": ["collect_candidates_before_source_dominance_audit"],
        }

    dominant_source_id = max(stats, key=lambda source_id: int(stats[source_id]["candidate_count"]))
    dominant_share = _ratio(int(stats[dominant_source_id]["candidate_count"]), total_candidates)
    document_counts = Counter(
        {source_id: int(item["document_count"]) for source_id, item in stats.items()}
    )
    max_document_count = max(document_counts.values()) if document_counts else 0

    risk_flags: list[str] = []
    recommended_actions: list[str] = []
    source_output: dict[str, dict[str, Any]] = {}

    for source_id, item in stats.items():
        candidate_count = int(item["candidate_count"])
        share = _ratio(candidate_count, total_candidates)
        reasons: list[str] = []
        if source_id == dominant_source_id and share >= 0.5:
            reasons.append("volume_advantage")
        if int(item["document_count"]) > 0 and int(item["document_count"]) == max_document_count:
            reasons.append("fetch_advantage")
        if int(item["title_heat_word_count"]) > 0:
            reasons.append("language_advantage")
        if int(item["real_engagement_count"]) > 0:
            reasons.append("real_engagement_advantage")
        elif int(item["title_heat_word_count"]) > 0:
            reasons.append("false_heat_advantage")
        if int(item["noise_candidate_count"]) > 0:
            reasons.append("noise_advantage")

        metrics = {
            "candidate_share": share,
            "document_coverage": _ratio(int(item["document_count"]), candidate_count),
            "title_heat_word_ratio": _ratio(int(item["title_heat_word_count"]), candidate_count),
            "real_engagement_ratio": _ratio(int(item["real_engagement_count"]), candidate_count),
            "noise_ratio": _ratio(int(item["noise_candidate_count"]), candidate_count),
        }
        source_output[source_id] = {
            **item,
            "candidate_share": share,
            "reasons": reasons,
            "metrics": metrics,
        }

    dominant_reasons = source_output[dominant_source_id]["reasons"]
    if dominant_share >= 0.67:
        risk_flags.append("single_source_dominance")
        recommended_actions.append("apply_soft_source_cap")
    if "false_heat_advantage" in dominant_reasons:
        risk_flags.append("false_heat_dominance")
        recommended_actions.append("do_not_treat_title_heat_words_as_social_heat")
    if "noise_advantage" in dominant_reasons:
        risk_flags.append("noise_dominance")
        recommended_actions.append("tighten_candidate_type_gate")
    if "real_engagement_advantage" in dominant_reasons:
        recommended_actions.append("keep_real_engagement_but_apply_source_cap")
    if not any("real_engagement_advantage" in item["reasons"] for item in source_output.values()):
        risk_flags.append("needs_real_social_heat")
        recommended_actions.append("collect_social_heat_observations_before_boosting")

    return {
        "version": "1.0.0",
        "summary": (
            f"{dominant_source_id} contributes {dominant_share:.0%} of "
            f"{total_candidates} candidates in this audit."
        ),
        "dominant_source_id": dominant_source_id,
        "dominant_source_share": dominant_share,
        "sources": source_output,
        "risk_flags": sorted(set(risk_flags)),
        "recommended_actions": sorted(set(recommended_actions)),
    }
