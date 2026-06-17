"""Markdown briefing generation from structured pipeline state."""

from __future__ import annotations

from typing import Any


STATUS_LABELS = {
    "verified": "已验证",
    "likely": "证据支持",
    "credible_rumor": "可信爆料",
    "weak_rumor": "弱流言",
    "unverified_rumor": "未证实流言",
    "rumor": "流言",
    "conflict": "证据冲突",
    "reject": "不采用",
    "manual_review_required": "待人工复核",
    "unchecked": "未核查",
}

MAIN_STATUSES = {"verified", "likely", "credible_rumor", "weak_rumor", "rumor"}
STAGE_LABELS = {
    "source_collection": "来源采集",
    "candidate_filtering": "候选过滤",
    "evidence_fetch": "正文证据",
    "claim_verification": "Claim核查",
    "story_selection": "Story选择",
    "platform_packaging": "平台文案",
}


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status or "未知")


def _first_url(item: dict[str, Any]) -> str:
    urls = item.get("source_urls", [])
    if isinstance(urls, list) and urls:
        return str(urls[0])
    metadata = item.get("metadata", {})
    if isinstance(metadata, dict):
        return str(metadata.get("candidate_url", ""))
    return ""


def _shorten(text: Any, limit: int = 180) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _evidence_quote(item: dict[str, Any]) -> str:
    evidence = item.get("evidence", [])
    if isinstance(evidence, list) and evidence:
        first = evidence[0]
        if isinstance(first, dict):
            return _shorten(first.get("quote", ""))
    return ""


def _has_synthetic_evidence(state: dict[str, Any]) -> bool:
    if state.get("dry_run"):
        return True
    for item in state.get("claim_verifications", []):
        for evidence in item.get("evidence", []):
            if isinstance(evidence, dict):
                metadata = evidence.get("metadata", {})
                if isinstance(metadata, dict) and metadata.get("dry_run_synthetic"):
                    return True
    return False


def _theme_candidate_pool_count(state: dict[str, Any]) -> int:
    pool = state.get("theme_candidate_pool", {})
    if not isinstance(pool, dict):
        return 0
    value = pool.get("candidate_pool_count", 0)
    return int(value) if isinstance(value, int) else 0


def _rationale(item: dict[str, Any]) -> str:
    llm = item.get("llm_verification", {})
    if isinstance(llm, dict) and llm.get("rationale"):
        return _shorten(llm["rationale"], 240)
    if item.get("rationale"):
        return _shorten(item["rationale"], 240)
    reasons = item.get("verification_reasons", [])
    if isinstance(reasons, list) and reasons:
        return ", ".join(str(reason) for reason in reasons)
    return "暂无说明。"


def _risk_flags(item: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    for key in ("risk_flags", "missing_fields"):
        values = item.get(key, [])
        if isinstance(values, list):
            flags.extend(str(value) for value in values if str(value).strip())
    llm = item.get("llm_verification", {})
    if isinstance(llm, dict):
        values = llm.get("risk_flags", [])
        if isinstance(values, list):
            flags.extend(str(value) for value in values if str(value).strip())
    return list(dict.fromkeys(flags))


def _heat_for_claim(item: dict[str, Any]) -> Any:
    metadata = item.get("metadata", {})
    if isinstance(metadata, dict):
        return metadata.get("heat_score", "")
    return ""


def _render_claim_item(item: dict[str, Any], index: int) -> list[str]:
    status = str(item.get("check_status", "unchecked"))
    confidence = item.get("confidence", 0)
    heat_score = _heat_for_claim(item)
    url = _first_url(item)
    quote = _evidence_quote(item)
    risks = _risk_flags(item)
    title = str(item.get("text", "未命名线索"))

    lines = [
        f"{index}. **{title}**",
        f"   - 状态：{_status_label(status)} / 置信度：{confidence}",
    ]
    if heat_score != "":
        lines.append(f"   - 热度：{heat_score}")
    lines.append(f"   - 判断依据：{_rationale(item)}")
    if quote:
        lines.append(f"   - 证据摘录：{quote}")
    if risks:
        lines.append(f"   - 风险标记：{', '.join(risks)}")
    if url:
        lines.append(f"   - 来源：{url}")
    return lines


def _artifact_line(state: dict[str, Any], label: str, key: str) -> str:
    value = state.get(key, "")
    return f"- {label}: `{value}`" if value else f"- {label}: 未生成"


def _first_claim(story: dict[str, Any]) -> dict[str, Any]:
    claims = story.get("claims", [])
    if isinstance(claims, list) and claims and isinstance(claims[0], dict):
        return claims[0]
    return {}


def _render_story_item(story: dict[str, Any], index: int) -> list[str]:
    claim = _first_claim(story)
    status = str(claim.get("check_status", story.get("status", "unknown")))
    confidence = claim.get("confidence", "未知")
    source_urls = story.get("source_urls", [])
    url = str(source_urls[0]) if isinstance(source_urls, list) and source_urls else ""
    discussion = story.get("discussion_score", "")
    title = str(story.get("title", "未命名 story"))
    lines = [
        f"{index}. **{title}**",
        f"   - 分类：{story.get('theme_section', 'supplemental')} / {story.get('category', 'unknown')}",
        f"   - 状态：{_status_label(status)} / 置信度：{confidence}",
        f"   - 综合分：{story.get('story_score', '未生成')}",
    ]
    if discussion != "":
        lines.append(f"   - 讨论热度：{discussion} / {story.get('discussion_level', 'none')}")
    preference = story.get("source_preference")
    if preference:
        lines.append(f"   - 来源选择：{preference}")
    quote = _evidence_quote(claim)
    if quote:
        lines.append(f"   - 证据摘录：{quote}")
    if url:
        lines.append(f"   - 来源：{url}")
    return lines


def _theme_sections_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    theme_sections = state.get("theme_sections", {})
    if not isinstance(theme_sections, dict):
        return []
    sections = theme_sections.get("sections", [])
    if not isinstance(sections, list):
        return []
    return [section for section in sections if isinstance(section, dict)]


def build_briefing_markdown(
    state: dict[str, Any],
    *,
    generated_at: str,
) -> str:
    verifications = [
        item
        for item in state.get("claim_verifications", [])
        if isinstance(item, dict)
    ]
    main_items = [
        item
        for item in verifications
        if str(item.get("check_status", "")) in MAIN_STATUSES
    ]
    review_items = [
        item
        for item in verifications
        if str(item.get("check_status", "")) not in MAIN_STATUSES
    ]
    quality_report = state.get("content_quality_report", {})
    quality_issues = []
    stage_scores = {}
    if isinstance(quality_report, dict):
        raw_issues = quality_report.get("issues", [])
        if isinstance(raw_issues, list):
            quality_issues = [item for item in raw_issues if isinstance(item, dict)]
        raw_stage_scores = quality_report.get("stage_scores", {})
        if isinstance(raw_stage_scores, dict):
            stage_scores = {
                str(key): value
                for key, value in raw_stage_scores.items()
                if isinstance(value, dict)
            }

    lines = [
        "# 48小时游戏资讯简报",
        "",
        f"- Topic: {state.get('topic', 'games')}",
        f"- Lookback hours: {state.get('lookback_hours', 48)}",
        f"- Generated at: {generated_at}",
        "",
    ]

    if _has_synthetic_evidence(state):
        lines.extend(
            [
                "> 流程验证输出：包含 dry-run 或合成证据，仅用于检查管线，不可直接发布。",
                "",
            ]
        )

    lines.extend(
        [
            "## 本轮概览",
            "",
            f"- 主候选：{len(state.get('candidates', []))}",
            f"- 补充池：{len(state.get('supplemental_candidates', []))}",
            f"- 主题预抓取候选池：{_theme_candidate_pool_count(state)}",
            f"- 过滤线索：{len(state.get('rejected_candidates', []))}",
            f"- Claim：{len(state.get('claims', []))}",
            f"- Claim verification：{len(verifications)}",
            f"- Stories：{len(state.get('stories', []))}",
            f"- Platform posts：{len(state.get('platform_posts', []))}",
            f"- Content quality gate：{quality_report.get('gate_status', '未生成') if isinstance(quality_report, dict) else '未生成'}",
            f"- Content quality score：{quality_report.get('overall_score', '未生成') if isinstance(quality_report, dict) else '未生成'}",
            f"- Content readiness：{quality_report.get('readiness', '未生成') if isinstance(quality_report, dict) else '未生成'}",
            f"- Content quality issues：{len(quality_issues)}",
            f"- LLM verification requests：{len(state.get('llm_verification_requests', []))}",
            f"- LLM verification results：{len(state.get('llm_verification_results', []))}",
            "",
            "## 主简报候选",
            "",
        ]
    )

    theme_sections = _theme_sections_from_state(state)
    if theme_sections:
        lines[-2] = "## 主题简报候选"
        for section in theme_sections:
            label = str(section.get("label") or section.get("id") or "未分类")
            candidate_count = section.get("candidate_count", 0)
            pool_count = section.get("pool_count", 0)
            selected_count = section.get("selected_count", 0)
            lines.extend(
                [
                    f"### {label}",
                    "",
                    f"- 板块候选：{candidate_count} / 入池：{pool_count} / 入选：{selected_count}",
                    "",
                ]
            )
            stories = [story for story in section.get("stories", []) if isinstance(story, dict)]
            if stories:
                for index, story in enumerate(stories, start=1):
                    lines.extend(_render_story_item(story, index))
                    lines.append("")
            else:
                lines.extend(["- 本轮暂无入选故事。", ""])
    elif main_items:
        for index, item in enumerate(main_items, start=1):
            lines.extend(_render_claim_item(item, index))
            lines.append("")
    else:
        lines.extend(["- 暂无可进入主简报的候选。", ""])

    if review_items:
        lines.extend(["## 待复核线索", ""])
        for index, item in enumerate(review_items, start=1):
            lines.extend(_render_claim_item(item, index))
            lines.append("")

    if stage_scores:
        lines.extend(["## 环节评分", ""])
        for key, label in STAGE_LABELS.items():
            stage = stage_scores.get(key, {})
            if stage:
                lines.append(
                    f"- {label}: {stage.get('score', '未生成')} / "
                    f"{stage.get('status', 'unknown')} - {stage.get('message', '')}"
                )
        lines.append("")

    if quality_issues:
        lines.extend(["## 内容质量检查", ""])
        for issue in quality_issues[:5]:
            lines.append(
                f"- {issue.get('severity', 'warning')} / {issue.get('code', 'unknown')}: "
                f"{issue.get('message', '')}"
            )
        lines.append("")

    lines.extend(
        [
            "## 产物索引",
            "",
            _artifact_line(state, "候选", "candidates_path"),
            _artifact_line(state, "补充池", "supplemental_candidates_path"),
            _artifact_line(state, "来源主题计数", "source_theme_counts_path"),
            _artifact_line(state, "主题候选池", "theme_candidate_pool_path"),
            _artifact_line(state, "正文", "documents_path"),
            _artifact_line(state, "证据块", "evidence_chunks_path"),
            _artifact_line(state, "上下文包", "context_packs_path"),
            _artifact_line(state, "Story clusters", "story_clusters_path"),
            _artifact_line(state, "Story candidates", "story_candidates_path"),
            _artifact_line(state, "Theme sections", "theme_sections_path"),
            _artifact_line(state, "Claims", "claims_path"),
            _artifact_line(state, "Claim verifications", "claim_verifications_path"),
            _artifact_line(state, "Stories", "stories_path"),
            _artifact_line(state, "Editorial judgment requests", "editorial_judgment_requests_path"),
            _artifact_line(state, "Assets", "assets_path"),
            _artifact_line(state, "Platform posts", "platform_posts_path"),
            _artifact_line(state, "Content quality report", "content_quality_report_path"),
            _artifact_line(state, "Content review", "content_review_path"),
            _artifact_line(state, "Human review template", "human_review_template_path"),
            _artifact_line(state, "Material bundle", "material_bundle_path"),
            _artifact_line(state, "LLM verification requests", "llm_verification_requests_path"),
            _artifact_line(state, "LLM verification results", "llm_verification_results_path"),
            _artifact_line(state, "原始线索", "raw_sources_path"),
            "",
            "## 下一步建议",
            "",
        ]
    )
    if quality_issues:
        recommendations = []
        if isinstance(quality_report, dict):
            raw_recommendations = quality_report.get("recommendations", [])
            if isinstance(raw_recommendations, list):
                recommendations = [str(item) for item in raw_recommendations if str(item).strip()]
        for recommendation in recommendations[:5]:
            lines.append(f"- {recommendation}")
    else:
        lines.extend(
            [
                "- 检查 Platform posts 中的流言标签、素材状态和平台文案，再交给内容质量验证。",
                "- 对 weak_rumor/unverified_rumor/conflict/manual_review_required 保留待复核标签。",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"
