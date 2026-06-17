"""Content quality validation for generated news artifacts."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONTENT_QUALITY_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "content_quality.yaml"
)

# Hardcoded fallback defaults — kept in sync with content_quality.yaml
_DEFAULT_GATE_THRESHOLDS: dict[str, int] = {
    "pass": 85,
    "needs_review": 60,
}


def load_gate_thresholds(config_path: Path | None = None) -> dict[str, int]:
    """Load content quality gate thresholds from a YAML config file.

    Falls back to hardcoded defaults if the file is missing, unreadable,
    or missing the ``gate_thresholds`` key.

    Parameters
    ----------
    config_path:
        Optional path to a ``content_quality.yaml`` file.  Defaults to
        ``<project-root>/LangGraph/config/content_quality.yaml``.

    Returns
    -------
    dict[str, int]
        Gate thresholds with keys ``pass`` and ``needs_review``.
    """
    path = config_path or DEFAULT_CONTENT_QUALITY_CONFIG_PATH
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except (FileNotFoundError, yaml.YAMLError, OSError) as exc:
        logger.warning(
            "Could not load gate thresholds from %s — using hardcoded defaults (%s)",
            path,
            exc,
        )
        return dict(_DEFAULT_GATE_THRESHOLDS)

    thresholds = raw.get("gate_thresholds")
    if not isinstance(thresholds, dict):
        logger.warning(
            "%s is missing the 'gate_thresholds' key — using hardcoded defaults", path
        )
        return dict(_DEFAULT_GATE_THRESHOLDS)

    merged = dict(_DEFAULT_GATE_THRESHOLDS)
    for key in ("pass", "needs_review"):
        if key in thresholds:
            merged[key] = int(thresholds[key])

    return merged


# Module-level gate thresholds loaded from config (with hardcoded fallback)
_GATE_THRESHOLDS: dict[str, int] = load_gate_thresholds()

# Active thresholds used by scoring functions — initialized from config,
# overridden by state in build_content_quality_report(), then reset.
_ACTIVE_THRESHOLDS: dict[str, int] = dict(_GATE_THRESHOLDS)


def _set_active_thresholds(pass_threshold: int, review_threshold: int) -> None:
    """Temporarily override active gate thresholds for the current build call."""
    _ACTIVE_THRESHOLDS["pass"] = pass_threshold
    _ACTIVE_THRESHOLDS["needs_review"] = review_threshold


def _reset_active_thresholds() -> None:
    """Reset active thresholds to config defaults."""
    _ACTIVE_THRESHOLDS["pass"] = _GATE_THRESHOLDS["pass"]
    _ACTIVE_THRESHOLDS["needs_review"] = _GATE_THRESHOLDS["needs_review"]


def _resolve_thresholds(state: dict[str, Any] | None = None) -> dict[str, int]:
    """Resolve gate thresholds, preferring state overrides over config defaults."""
    pass_threshold = int(_GATE_THRESHOLDS["pass"])
    review_threshold = int(_GATE_THRESHOLDS["needs_review"])
    if state:
        state_pass = state.get("content_quality_pass_threshold")
        if state_pass is not None:
            pass_threshold = int(state_pass)
        state_review = state.get("content_quality_review_threshold")
        if state_review is not None:
            review_threshold = int(state_review)
    return {"pass": pass_threshold, "needs_review": review_threshold}


RUMOR_STATUSES = {"credible_rumor", "weak_rumor", "unverified_rumor", "rumor"}


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _stage_status(score: int) -> str:
    if score >= _ACTIVE_THRESHOLDS["pass"]:
        return "pass"
    if score >= _ACTIVE_THRESHOLDS["needs_review"]:
        return "needs_review"
    return "blocked"


def _criterion(score: float, weight: float, message: str) -> dict[str, Any]:
    return {
        "score": _clamp_score(score),
        "weight": weight,
        "message": message,
    }


def _weighted_criteria_score(criteria: dict[str, dict[str, Any]]) -> int:
    total_weight = sum(float(item.get("weight", 0)) for item in criteria.values())
    if total_weight <= 0:
        return 0
    score = 0.0
    for item in criteria.values():
        score += float(item.get("score", 0)) * float(item.get("weight", 0))
    return _clamp_score(score / total_weight)


def _stage(
    score: float,
    message: str,
    metrics: dict[str, Any],
    criteria: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    final_score = _clamp_score(score)
    return {
        "score": final_score,
        "status": _stage_status(final_score),
        "message": message,
        "metrics": metrics,
        "criteria": criteria or {},
    }


def _issue(code: str, severity: str, message: str, recommendation: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "recommendation": recommendation,
    }


def _has_heat_signals(candidate: dict[str, Any]) -> bool:
    signals = candidate.get("heat_signals", {})
    if not isinstance(signals, dict):
        return False
    return any(value not in ("", None, 0, [], {}) for value in signals.values())


def _has_discussion_signals(candidate: dict[str, Any]) -> bool:
    profile = candidate.get("discussion_profile", {})
    if isinstance(profile, dict):
        score = profile.get("score", 0)
        if not isinstance(score, (int, float)):
            score = 0
        if (
            profile.get("level") in {"discussed", "trending"}
            or profile.get("has_direct_engagement")
            or profile.get("has_multi_platform_discussion")
            or float(score) >= 35
        ):
            return True

    signals = candidate.get("heat_signals", {})
    if not isinstance(signals, dict):
        return False
    for key in ("comments", "shares", "reposts", "danmaku"):
        value = signals.get(key, 0)
        if isinstance(value, (int, float)) and value > 0:
            return True
    return False


def _ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def _domain_from_url(url: Any) -> str:
    parsed = urlparse(str(url))
    return parsed.netloc.lower().removeprefix("www.")


def _source_distribution(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for candidate in candidates:
        source_id = str(candidate.get("source_id", "")).strip() or "unknown"
        counts[source_id] += 1
    return dict(counts)


def _story_source_distribution(stories: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for story in stories:
        urls = story.get("source_urls", [])
        if isinstance(urls, list) and urls:
            domain = _domain_from_url(urls[0]) or "unknown"
        else:
            domain = "unknown"
        counts[domain] += 1
    return dict(counts)


def _dominant_share(distribution: dict[str, int]) -> float:
    total = sum(distribution.values())
    if total <= 0:
        return 0.0
    return round(max(distribution.values()) / total, 4)


def _story_has_rumor(story: dict[str, Any]) -> bool:
    for claim in story.get("claims", []):
        if isinstance(claim, dict) and str(claim.get("check_status", "")) in RUMOR_STATUSES:
            return True
    return False


def _post_has_rumor(post: dict[str, Any]) -> bool:
    return str(post.get("internal_status", "")) in RUMOR_STATUSES or "流言" in post.get("public_labels", [])


def _source_health_summary(state: dict[str, Any]) -> dict[str, int]:
    source_health = state.get("source_health", {})
    if not isinstance(source_health, dict):
        return {}
    summary = source_health.get("summary", {})
    if not isinstance(summary, dict):
        return {}
    return {
        "healthy": int(summary.get("healthy", 0) or 0),
        "needs_fill": int(summary.get("needs_fill", 0) or 0),
        "source_blocked": int(summary.get("source_blocked", 0) or 0),
        "source_broken": int(summary.get("source_broken", 0) or 0),
    }


def _source_collection_score(source_health: dict[str, int], candidate_count: int) -> dict[str, Any]:
    total_sources = sum(source_health.values())
    if total_sources > 0:
        healthy = source_health.get("healthy", 0)
        needs_fill = source_health.get("needs_fill", 0)
        healthy_ratio = healthy / total_sources
        blocked_ratio = (source_health.get("source_blocked", 0) + source_health.get("source_broken", 0)) / total_sources
        fill_ratio = needs_fill / total_sources
        criteria = {
            "healthy_source_ratio": _criterion(healthy_ratio * 100, 0.7, "真实来源健康比例。"),
            "blocked_source_penalty": _criterion((1 - blocked_ratio) * 100, 0.2, "来源阻塞或结构损坏越少越好。"),
            "manual_fill_penalty": _criterion((1 - fill_ratio) * 100, 0.1, "需要人工补源越少越好。"),
        }
        score = _weighted_criteria_score(criteria)
        message = f"{healthy}/{total_sources} 个真实来源健康。"
    elif candidate_count:
        criteria = {
            "healthy_source_ratio": _criterion(60, 1.0, "有候选但缺 source health，按 dry-run/旧 artifact 复盘处理。"),
        }
        score = _weighted_criteria_score(criteria)
        message = "本轮有候选，但没有 source health；通常表示 dry-run 或旧 artifact 复盘。"
    else:
        criteria = {
            "healthy_source_ratio": _criterion(0, 1.0, "没有来源健康信息，也没有候选。"),
        }
        score = 0
        message = "没有可用来源健康信息，也没有候选。"
    return _stage(score, message, {"source_health": source_health}, criteria)


def _candidate_filtering_score(
    *,
    candidate_count: int,
    supplemental_count: int,
    rejected_count: int,
    dominant_share: float,
    heat_signal_coverage: float,
    discussion_signal_coverage: float,
) -> dict[str, Any]:
    if candidate_count <= 0:
        criteria = {
            "candidate_volume": _criterion(0, 0.5, "没有主候选。"),
            "source_diversity": _criterion(0, 0.3, "没有可评估来源多样性。"),
            "lane_separation": _criterion(0, 0.2, "没有候选分流。"),
        }
        return _stage(
            0,
            "没有主候选，无法进入后续内容生产。",
            {
                "candidates": candidate_count,
                "supplemental_candidates": supplemental_count,
                "rejected_candidates": rejected_count,
            },
            criteria,
        )
    lane_score = 100 if supplemental_count or rejected_count else 60
    criteria = {
        "candidate_volume": _criterion(min(100, candidate_count * 10), 0.25, "主候选数量是否足够进入内容生产。"),
        "source_diversity": _criterion((1 - dominant_share) * 100, 0.35, "候选来源越不集中越好。"),
        "lane_separation": _criterion(lane_score, 0.2, "是否完成主候选、补充池、拒绝池分流。"),
        "discussion_signal_support": _criterion(
            discussion_signal_coverage * 100,
            0.2,
            "是否有评论、转发、弹幕或多平台讨论证据支撑。",
        ),
    }
    score = _weighted_criteria_score(criteria)
    return _stage(
        score,
        "候选已进入主/补充/拒绝分流；分数主要受来源集中度和热度信号影响。",
        {
            "candidates": candidate_count,
            "supplemental_candidates": supplemental_count,
            "rejected_candidates": rejected_count,
            "dominant_source_share": dominant_share,
            "heat_signal_coverage": heat_signal_coverage,
            "discussion_signal_coverage": discussion_signal_coverage,
        },
        criteria,
    )


def _evidence_fetch_score(document_fetch_coverage: float, document_count: int) -> dict[str, Any]:
    coverage_score = document_fetch_coverage * 100
    minimum_depth_score = min(100, document_count * 12)
    criteria = {
        "document_coverage": _criterion(coverage_score, 0.65, "主候选正文抓取覆盖率。"),
        "minimum_evidence_depth": _criterion(minimum_depth_score, 0.35, "至少抓取若干篇正文用于内容验证。"),
    }
    score = _weighted_criteria_score(criteria)
    if document_count >= 5:
        score = max(score, 60)
    return _stage(
        score,
        "正文抓取覆盖决定证据链是否足够支撑内容评估。",
        {
            "documents": document_count,
            "document_fetch_coverage": document_fetch_coverage,
        },
        criteria,
    )


def _claim_verification_score(
    *,
    verification_count: int,
    llm_request_count: int,
    llm_result_count: int,
    rumor_story_count: int,
    rumor_post_count: int,
) -> dict[str, Any]:
    if verification_count <= 0:
        criteria = {
            "rule_verification_coverage": _criterion(0, 0.45, "没有规则核查结果。"),
            "llm_or_manual_coverage": _criterion(0, 0.4, "没有 LLM/人工语义核查。"),
            "rumor_safety": _criterion(0, 0.15, "没有流言安全判断。"),
        }
        return _stage(
            0,
            "没有 claim verification，无法评估事实链路。",
            {"claim_verifications": verification_count},
            criteria,
        )
    if llm_request_count > 0:
        llm_coverage = llm_result_count / llm_request_count
    else:
        llm_coverage = 1.0
    rumor_safety = 0 if (rumor_story_count or rumor_post_count) and llm_result_count == 0 else 100
    criteria = {
        "rule_verification_coverage": _criterion(100, 0.35, "已有规则版 claim verification。"),
        "llm_or_manual_coverage": _criterion(llm_coverage * 100, 0.45, "LLM 或人工语义核查覆盖率。"),
        "rumor_safety": _criterion(rumor_safety, 0.2, "流言类 story 是否经过语义复核。"),
    }
    score = _weighted_criteria_score(criteria)
    return _stage(
        score,
        "claim 核查分数由规则核查覆盖和 LLM/人工语义核查覆盖共同决定。",
        {
            "claim_verifications": verification_count,
            "llm_verification_requests": llm_request_count,
            "llm_verification_results": llm_result_count,
            "llm_coverage": round(llm_coverage, 4),
            "rumor_story_count": rumor_story_count,
            "rumor_post_count": rumor_post_count,
        },
        criteria,
    )


def _story_selection_score(story_count: int, dominant_share: float) -> dict[str, Any]:
    if story_count <= 0:
        criteria = {
            "story_volume": _criterion(0, 0.45, "没有 story 入选。"),
            "story_source_diversity": _criterion(0, 0.4, "没有 story 来源多样性。"),
            "briefing_focus": _criterion(0, 0.15, "没有可评估简报焦点。"),
        }
        return _stage(
            0,
            "没有 story 入选，不能进入内容包装。",
            {"stories": story_count, "dominant_source_share": dominant_share},
            criteria,
        )
    criteria = {
        "story_volume": _criterion(min(100, story_count * 25), 0.35, "入选 story 数量是否足够形成简报。"),
        "story_source_diversity": _criterion((1 - dominant_share) * 100, 0.45, "入选 story 是否避免单源主导。"),
        "briefing_focus": _criterion(80 if story_count <= 8 else 60, 0.2, "story 数量是否适合人工复核和简报聚焦。"),
    }
    score = _weighted_criteria_score(criteria)
    return _stage(
        score,
        "story 选择分数主要看是否有足够内容，以及入选故事是否被单一来源主导。",
        {"stories": story_count, "dominant_source_share": dominant_share},
        criteria,
    )


def _platform_packaging_score(
    *,
    story_count: int,
    platform_post_count: int,
    manual_asset_ratio: float,
) -> dict[str, Any]:
    if story_count and not platform_post_count:
        criteria = {
            "copy_coverage": _criterion(0, 0.55, "story 没有对应平台文案。"),
            "asset_readiness": _criterion(0, 0.3, "素材未准备。"),
            "reviewability": _criterion(0, 0.15, "不可进行平台文案复核。"),
        }
        return _stage(
            0,
            "已有 story 但没有平台文案。",
            {"stories": story_count, "platform_posts": platform_post_count},
            criteria,
        )
    if not platform_post_count:
        criteria = {
            "copy_coverage": _criterion(50, 1.0, "没有 story 时平台文案不是阻塞项。"),
        }
        return _stage(
            50,
            "没有平台文案；如果本轮没有 story，这不是阻塞项。",
            {"stories": story_count, "platform_posts": platform_post_count},
            criteria,
        )
    copy_coverage = min(1.0, platform_post_count / max(story_count, 1))
    criteria = {
        "copy_coverage": _criterion(copy_coverage * 100, 0.45, "story 是否都有平台文案。"),
        "asset_readiness": _criterion((1 - manual_asset_ratio) * 100, 0.35, "素材是否无需人工补齐。"),
        "reviewability": _criterion(85, 0.2, "文案是否足以供人工复核。"),
    }
    score = _weighted_criteria_score(criteria)
    return _stage(
        score,
        "平台包装分数只评价文案与素材准备度，不评价最终排版效果。",
        {
            "stories": story_count,
            "platform_posts": platform_post_count,
            "manual_asset_ratio": manual_asset_ratio,
        },
        criteria,
    )


def _weighted_overall(stage_scores: dict[str, dict[str, Any]]) -> int:
    weights = {
        "source_collection": 0.15,
        "candidate_filtering": 0.15,
        "evidence_fetch": 0.20,
        "claim_verification": 0.25,
        "story_selection": 0.15,
        "platform_packaging": 0.10,
    }
    total = 0.0
    for name, weight in weights.items():
        total += stage_scores[name]["score"] * weight
    return _clamp_score(total)


def _readiness(gate_status: str, overall_score: int, issues: list[dict[str, str]]) -> str:
    if gate_status == "blocked":
        return "blocked"
    if not issues and overall_score >= _ACTIVE_THRESHOLDS["pass"]:
        return "ready_for_layout"
    return "ready_for_content_review"


def build_content_quality_report(state: dict[str, Any]) -> dict[str, Any]:
    # Resolve active thresholds from state overrides, falling back to config/file defaults
    resolved = _resolve_thresholds(state)
    _set_active_thresholds(resolved["pass"], resolved["needs_review"])

    candidates = [item for item in state.get("candidates", []) if isinstance(item, dict)]
    supplemental = [item for item in state.get("supplemental_candidates", []) if isinstance(item, dict)]
    rejected = [item for item in state.get("rejected_candidates", []) if isinstance(item, dict)]
    documents = [item for item in state.get("documents", []) if isinstance(item, dict)]
    verifications = [item for item in state.get("claim_verifications", []) if isinstance(item, dict)]
    stories = [item for item in state.get("stories", []) if isinstance(item, dict)]
    platform_posts = [item for item in state.get("platform_posts", []) if isinstance(item, dict)]
    llm_requests = [item for item in state.get("llm_verification_requests", []) if isinstance(item, dict)]
    llm_results = [item for item in state.get("llm_verification_results", []) if isinstance(item, dict)]
    theme_candidate_pool = state.get("theme_candidate_pool", {})
    if not isinstance(theme_candidate_pool, dict):
        theme_candidate_pool = {}
    theme_selected_candidates = [
        item
        for item in theme_candidate_pool.get("selected_candidates", [])
        if isinstance(item, dict)
    ]
    theme_fetch_candidates = [
        item
        for item in theme_candidate_pool.get("fetch_candidates", [])
        if isinstance(item, dict)
    ]
    theme_sections = [
        item
        for item in theme_candidate_pool.get("sections", [])
        if isinstance(item, dict)
    ]
    source_health = _source_health_summary(state)

    heat_signal_count = sum(1 for item in candidates if _has_heat_signals(item))
    discussion_signal_count = sum(1 for item in candidates if _has_discussion_signals(item))
    candidate_sources = _source_distribution(candidates)
    story_sources = _story_source_distribution(stories)
    rumor_story_count = sum(1 for item in stories if _story_has_rumor(item))
    rumor_post_count = sum(1 for item in platform_posts if _post_has_rumor(item))
    manual_asset_count = sum(1 for item in platform_posts if item.get("asset_status") == "manual_fill_required")

    fetch_candidate_count = int(
        theme_candidate_pool.get("fetch_selected_count") or len(theme_fetch_candidates) or 0
    )
    document_denominator = fetch_candidate_count or len(theme_selected_candidates) or len(candidates)
    metrics = {
        "candidate_sources": candidate_sources,
        "story_sources": story_sources,
        "candidate_source_dominant_share": _dominant_share(candidate_sources),
        "story_source_dominant_share": _dominant_share(story_sources),
        "heat_signal_coverage": _ratio(heat_signal_count, len(candidates)),
        "discussion_signal_coverage": _ratio(discussion_signal_count, len(candidates)),
        "document_fetch_coverage": _ratio(len(documents), document_denominator),
        "theme_candidate_pool_count": theme_candidate_pool.get("candidate_pool_count", 0),
        "theme_selected_candidate_count": len(theme_selected_candidates),
        "theme_fetch_candidate_count": fetch_candidate_count,
        "theme_section_pool_counts": {
            str(section.get("id", "")): section.get("pool_count", 0)
            for section in theme_sections
        },
        "story_to_candidate_ratio": _ratio(len(stories), len(candidates)),
        "rumor_story_count": rumor_story_count,
        "rumor_post_count": rumor_post_count,
        "manual_asset_ratio": _ratio(manual_asset_count, len(platform_posts)),
    }

    issues: list[dict[str, str]] = []
    if source_health.get("healthy", 0) == 0 and (
        source_health.get("source_blocked", 0) or source_health.get("source_broken", 0)
    ):
        issues.append(
            _issue(
                "source_collection_blocked",
                "error",
                "没有健康的真实来源，本轮内容不能作为真实资讯输出评估。",
                "先在可联网环境运行，或修复代理/防火墙，再进行内容质量评估。",
            )
        )
    if not candidates:
        issues.append(
            _issue(
                "no_main_candidates",
                "warning",
                "没有生成主候选。",
                "检查 source health、时间窗口、来源相关性过滤和候选类型过滤。",
            )
        )
    if len(candidates) >= 4 and metrics["discussion_signal_coverage"] < 0.4:
        issues.append(
            _issue(
                "low_discussion_signal_coverage",
                "warning",
                "多数候选缺少评论、转发、弹幕或多平台讨论证据，暂不能证明属于高热度讨论。",
                "先把它们视为新鲜媒体线索；接入社区/搜索热度采集后，再标成高热度故事。",
            )
        )
    if len(stories) >= 3 and metrics["story_source_dominant_share"] >= 0.67:
        issues.append(
            _issue(
                "single_source_story_dominance",
                "warning",
                "入选 story 被单一来源主导。",
                "在最终简报前加入单源数量上限或来源多样性评分。",
            )
        )
    if llm_requests and not llm_results:
        issues.append(
            _issue(
                "no_llm_verification_results",
                "warning",
                "已生成 LLM 核查请求，但没有应用 LLM 核查结果。",
                "对发布候选运行 LLM verifier；否则只能把结果视为规则预审，不可直接发布。",
            )
        )
    if (rumor_story_count or rumor_post_count) and not llm_results:
        issues.append(
            _issue(
                "rumor_without_llm_verification",
                "warning",
                "流言类 story 未经过语义 LLM 核查。",
                "流言进入可发布内容前，必须经过 LLM 或人工复核。",
            )
        )
    if candidates and len(documents) < min(len(candidates), 5):
        issues.append(
            _issue(
                "limited_document_fetch",
                "warning",
                "正文抓取覆盖较低，只核查了主候选中的一小部分。",
                "内容验证运行时提高 --document-fetch-limit。",
            )
        )
    if stories and not platform_posts:
        issues.append(
            _issue(
                "missing_platform_posts",
                "warning",
                "已有 stories，但没有生成平台文案草稿。",
                "先运行 PlatformWriter，再评估内容包装质量。",
            )
        )
    if platform_posts and manual_asset_count == len(platform_posts):
        issues.append(
            _issue(
                "manual_assets_required",
                "warning",
                "所有平台文案都需要手动补素材。",
                "现在先评估文字内容质量；素材抽取或占位合同稳定前，继续暂缓视觉发布。",
            )
        )

    if any(issue["severity"] == "error" for issue in issues):
        gate_status = "blocked"
    elif issues:
        gate_status = "needs_review"
    else:
        gate_status = "pass"

    stage_scores = {
        "source_collection": _source_collection_score(source_health, len(candidates)),
        "candidate_filtering": _candidate_filtering_score(
            candidate_count=len(candidates),
            supplemental_count=len(supplemental),
            rejected_count=len(rejected),
            dominant_share=metrics["candidate_source_dominant_share"],
            heat_signal_coverage=metrics["heat_signal_coverage"],
            discussion_signal_coverage=metrics["discussion_signal_coverage"],
        ),
        "evidence_fetch": _evidence_fetch_score(metrics["document_fetch_coverage"], len(documents)),
        "claim_verification": _claim_verification_score(
            verification_count=len(verifications),
            llm_request_count=len(llm_requests),
            llm_result_count=len(llm_results),
            rumor_story_count=rumor_story_count,
            rumor_post_count=rumor_post_count,
        ),
        "story_selection": _story_selection_score(len(stories), metrics["story_source_dominant_share"]),
        "platform_packaging": _platform_packaging_score(
            story_count=len(stories),
            platform_post_count=len(platform_posts),
            manual_asset_ratio=metrics["manual_asset_ratio"],
        ),
    }
    overall_score = _weighted_overall(stage_scores)

    try:
        return {
            "version": "0.1.0",
            "gate_status": gate_status,
            "overall_score": overall_score,
            "readiness": _readiness(gate_status, overall_score, issues),
            "final_scorecard": {
                "score": overall_score,
                "readiness": _readiness(gate_status, overall_score, issues),
                "policy": (
                    "Phase 5 requires overall_score >= "
                    f"{_ACTIVE_THRESHOLDS['pass']}, "
                    "readiness == ready_for_layout, and no blocked stage."
                ),
                "stage_weights": {
                    "source_collection": 0.15,
                    "candidate_filtering": 0.15,
                    "evidence_fetch": 0.20,
                    "claim_verification": 0.25,
                    "story_selection": 0.15,
                    "platform_packaging": 0.10,
                },
            },
            "summary": {
                "candidates": len(candidates),
                "supplemental_candidates": len(supplemental),
                "rejected_candidates": len(rejected),
                "theme_candidate_pool": theme_candidate_pool.get("candidate_pool_count", 0),
                "theme_selected_candidates": len(theme_selected_candidates),
                "theme_fetch_candidates": fetch_candidate_count,
                "documents": len(documents),
                "claim_verifications": len(verifications),
                "stories": len(stories),
                "platform_posts": len(platform_posts),
                "llm_verification_requests": len(llm_requests),
                "llm_verification_results": len(llm_results),
                "source_health": source_health,
            },
            "stage_scores": stage_scores,
            "metrics": metrics,
            "issues": issues,
            "recommendations": [issue["recommendation"] for issue in issues],
        }
    finally:
        _reset_active_thresholds()
