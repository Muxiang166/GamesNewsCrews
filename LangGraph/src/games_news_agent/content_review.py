"""Human review package generation for live content validation."""

from __future__ import annotations

from typing import Any


STAGE_LABELS = {
    "source_collection": "来源采集",
    "candidate_filtering": "候选过滤",
    "evidence_fetch": "正文证据",
    "claim_verification": "Claim 核查",
    "story_selection": "Story 选择",
    "platform_packaging": "平台文案",
}


def _shorten(text: Any, limit: int = 260) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _first_claim(story: dict[str, Any]) -> dict[str, Any]:
    claims = story.get("claims", [])
    if isinstance(claims, list) and claims and isinstance(claims[0], dict):
        return claims[0]
    return {}


def _first_evidence_quote(claim: dict[str, Any]) -> str:
    evidence = claim.get("evidence", [])
    if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict):
        return _shorten(evidence[0].get("quote", ""))
    return ""


def _discussion_profile(story: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
    profile = story.get("discussion_profile", {})
    if isinstance(profile, dict) and profile:
        return profile
    metadata = claim.get("metadata", {})
    if isinstance(metadata, dict):
        profile = metadata.get("discussion_profile", {})
        if isinstance(profile, dict):
            return profile
    return {}


def _discussion_score(story: dict[str, Any], profile: dict[str, Any]) -> Any:
    value = story.get("discussion_score")
    if value not in (None, ""):
        return value
    return profile.get("score", "未生成")


def _discussion_level(story: dict[str, Any], profile: dict[str, Any]) -> str:
    return str(story.get("discussion_level") or profile.get("level") or "none")


def _discussion_list(profile: dict[str, Any], key: str) -> str:
    values = profile.get(key, [])
    if not isinstance(values, list):
        return "暂无"
    cleaned = [str(item) for item in values if str(item).strip()]
    return ", ".join(cleaned[:6]) if cleaned else "暂无"


def _format_counts(counts: Any) -> str:
    if not isinstance(counts, dict) or not counts:
        return "暂无"
    parts = [f"{key}={value}" for key, value in counts.items()]
    return ", ".join(parts[:8])


def _format_list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "暂无"
    return ", ".join(str(item) for item in values[:8])


SECTION_LABELS = {
    "sony": "索尼",
    "nintendo": "任天堂",
    "microsoft": "微软",
    "pc": "PC",
    "supplemental": "补充板块",
}


def _post_by_story(platform_posts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    posts: dict[str, dict[str, Any]] = {}
    for post in platform_posts:
        story_id = str(post.get("story_id", ""))
        if story_id and story_id not in posts:
            posts[story_id] = post
    return posts


def _theme_sections_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    theme_sections = state.get("theme_sections", {})
    if not isinstance(theme_sections, dict):
        return []
    sections = theme_sections.get("sections", [])
    if not isinstance(sections, list):
        return []
    return [section for section in sections if isinstance(section, dict)]


def _render_story_review_lines(
    story: dict[str, Any],
    index: int,
    posts: dict[str, dict[str, Any]],
) -> list[str]:
    story_id = str(story.get("id", ""))
    claim = _first_claim(story)
    post = posts.get(story_id, {})
    label = str(post.get("public_label_text", ""))
    urls = story.get("source_urls", [])
    source = str(urls[0]) if isinstance(urls, list) and urls else "待补充"
    quote = _first_evidence_quote(claim)
    discussion_profile = _discussion_profile(story, claim)
    lines = [
        f"#### {index}. {story.get('title', '未命名 story')}",
        "",
        f"- Story ID：`{story_id}`",
        f"- 机器分：{story.get('story_score', '未生成')}",
        f"- 分类/状态：{story.get('category', 'unknown')} / {story.get('status', 'unknown')} {label}",
        f"- 来源：{source}",
        f"- Claim 状态：{claim.get('check_status', 'unknown')} / 置信度：{claim.get('confidence', '未知')}",
        f"- 讨论热度：{_discussion_score(story, discussion_profile)} / {_discussion_level(story, discussion_profile)}",
        f"- 讨论平台：{_discussion_list(discussion_profile, 'platforms')}",
        f"- 讨论依据：{_discussion_list(discussion_profile, 'reasons')}",
    ]
    if quote:
        lines.append(f"- 证据摘录：{quote}")
    platforms = post.get("platforms", {})
    if isinstance(platforms, dict):
        weibo = platforms.get("weibo", {})
        if isinstance(weibo, dict) and weibo.get("text"):
            lines.extend(["", "**文案预览**", "", _shorten(weibo.get("text"), 420)])
    lines.extend(
        [
            "",
            "| 用户评分项 | 分数(0-10) | 备注 |",
            "| --- | --- | --- |",
            "| 是否值得写 |  |  |",
            "| 是否符合48小时热点 |  |  |",
            "| 是否有趣/有梗/有传播潜力 |  |  |",
            "| 证据是否可信 |  |  |",
            "| 标题方向是否接近目标风格 |  |  |",
            "",
        ]
    )
    return lines


def build_human_review_template() -> dict[str, Any]:
    return {
        "version": "0.1.0",
        "reviewer": "",
        "preferred_direction": "",
        "style_target": {
            "tone": "",
            "examples_to_move_toward": [],
            "examples_to_avoid": [],
            "notes": "",
        },
        "stage_overrides": {
            "source_collection": None,
            "candidate_filtering": None,
            "evidence_fetch": None,
            "claim_verification": None,
            "story_selection": None,
            "platform_packaging": None,
        },
        "story_reviews": [],
        "final_decision": "continue_phase_4_5",
    }


def build_content_review_markdown(state: dict[str, Any]) -> str:
    quality = state.get("content_quality_report", {})
    if not isinstance(quality, dict):
        quality = {}
    stories = [item for item in state.get("stories", []) if isinstance(item, dict)]
    platform_posts = [item for item in state.get("platform_posts", []) if isinstance(item, dict)]
    posts = _post_by_story(platform_posts)
    stage_scores = quality.get("stage_scores", {})
    if not isinstance(stage_scores, dict):
        stage_scores = {}

    lines = [
        "# 内容质量人工评审包",
        "",
        f"- 整体机器分：{quality.get('overall_score', '未生成')}",
        f"- Readiness：{quality.get('readiness', '未生成')}",
        f"- Gate：{quality.get('gate_status', '未生成')}",
        "",
        "## 环节机器评分",
        "",
    ]
    for key, label in STAGE_LABELS.items():
        stage = stage_scores.get(key, {})
        if isinstance(stage, dict):
            lines.append(f"- {label}: {stage.get('score', '未生成')} / {stage.get('status', 'unknown')} - {stage.get('message', '')}")
    if not stage_scores:
        lines.append("- 暂无环节评分。")

    social_heat_summary = state.get("social_heat_summary", {})
    if isinstance(social_heat_summary, dict) and social_heat_summary:
        lines.extend(
            [
                "",
                "## 社交热度观测",
                "",
                f"- 观测总数：{social_heat_summary.get('total_observations', 0)}",
                f"- 平台分布：{_format_counts(social_heat_summary.get('platform_counts'))}",
                f"- 状态分布：{_format_counts(social_heat_summary.get('status_counts'))}",
                f"- 热度有效性：{_format_counts(social_heat_summary.get('heat_validity_counts'))}",
            ]
        )

    social_heat_relevance_summary = state.get("social_heat_relevance_summary", {})
    if isinstance(social_heat_relevance_summary, dict) and social_heat_relevance_summary:
        lines.extend(
            [
                "",
                "## 社交相关性检查",
                "",
                f"- 检查总数：{social_heat_relevance_summary.get('total_checks', 0)}",
                f"- 相关性分布：{_format_counts(social_heat_relevance_summary.get('status_counts'))}",
                f"- 时间提示：{_format_counts(social_heat_relevance_summary.get('time_hint_counts'))}",
                f"- 结果类型：{_format_counts(social_heat_relevance_summary.get('result_type_counts'))}",
                f"- 语义复核候选：{social_heat_relevance_summary.get('semantic_review_candidates', 0)}",
            ]
        )

    selection_stage_diagnostics = state.get("selection_stage_diagnostics", {})
    if isinstance(selection_stage_diagnostics, dict) and selection_stage_diagnostics:
        selection_summary = selection_stage_diagnostics.get("summary", {})
        if not isinstance(selection_summary, dict):
            selection_summary = {}
        lines.extend(
            [
                "",
                "## 采集后阶段诊断",
                "",
                f"- 瓶颈分布：{_format_counts(selection_summary.get('bottleneck_counts'))}",
            ]
        )
        sections = selection_stage_diagnostics.get("sections", {})
        if isinstance(sections, dict):
            for section_id in ("sony", "nintendo", "microsoft", "pc", "supplemental"):
                section = sections.get(section_id, {})
                if not isinstance(section, dict):
                    continue
                label = SECTION_LABELS.get(section_id, section_id)
                lines.append(
                    (
                        f"- {label}：源头主候选={section.get('source_main_count', 0)} / "
                        f"主题候选={section.get('candidate_count', 0)} / "
                        f"入池={section.get('pool_count', 0)} / "
                        f"取证={section.get('fetch_selected_count', 0)} / "
                        f"Context={section.get('context_pack_count', 0)} / "
                        f"Claim={section.get('claim_verification_count', 0)} / "
                        f"Story候选={section.get('story_candidate_count', 0)} / "
                        f"最终={section.get('final_selected_count', 0)} / "
                        f"瓶颈={section.get('primary_bottleneck', 'unknown')}"
                    )
                )

    source_dominance = state.get("source_dominance_audit", {})
    if isinstance(source_dominance, dict) and source_dominance:
        lines.extend(
            [
                "",
                "## 单源主导诊断",
                "",
                f"- 主导来源：{source_dominance.get('dominant_source_id', '未生成')}",
                f"- 主导占比：{source_dominance.get('dominant_source_share', '未生成')}",
                f"- 风险标记：{_format_list(source_dominance.get('risk_flags'))}",
                f"- 建议动作：{_format_list(source_dominance.get('recommended_actions'))}",
            ]
        )

    lines.extend(
        [
            "",
            "## 真实联网内容候选",
            "",
        ]
    )
    if not stories:
        lines.extend(["- 暂无 story 可供人工评价。", ""])
    theme_sections = _theme_sections_from_state(state)
    if stories and theme_sections:
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
            section_stories = [
                story for story in section.get("stories", []) if isinstance(story, dict)
            ]
            if section_stories:
                for index, story in enumerate(section_stories, start=1):
                    lines.extend(_render_story_review_lines(story, index, posts))
            else:
                lines.extend(["- 本轮暂无入选故事。", ""])
        stories = []
    for index, story in enumerate(stories, start=1):
        story_id = str(story.get("id", ""))
        claim = _first_claim(story)
        post = posts.get(story_id, {})
        label = str(post.get("public_label_text", ""))
        urls = story.get("source_urls", [])
        source = str(urls[0]) if isinstance(urls, list) and urls else "待补充"
        quote = _first_evidence_quote(claim)
        discussion_profile = _discussion_profile(story, claim)
        lines.extend(
            [
                f"### {index}. {story.get('title', '未命名 story')}",
                "",
                f"- Story ID：`{story_id}`",
                f"- 机器分：{story.get('story_score', '未生成')}",
                f"- 分类/状态：{story.get('category', 'unknown')} / {story.get('status', 'unknown')} {label}",
                f"- 来源：{source}",
                f"- Claim 状态：{claim.get('check_status', 'unknown')} / 置信度：{claim.get('confidence', '未知')}",
                f"- 讨论热度：{_discussion_score(story, discussion_profile)} / {_discussion_level(story, discussion_profile)}",
                f"- 讨论平台：{_discussion_list(discussion_profile, 'platforms')}",
                f"- 讨论依据：{_discussion_list(discussion_profile, 'reasons')}",
            ]
        )
        if quote:
            lines.append(f"- 证据摘录：{quote}")
        platforms = post.get("platforms", {})
        if isinstance(platforms, dict):
            weibo = platforms.get("weibo", {})
            if isinstance(weibo, dict) and weibo.get("text"):
                lines.extend(["", "**文案预览**", "", _shorten(weibo.get("text"), 420)])
        lines.extend(
            [
                "",
                "| 用户评分项 | 分数(0-10) | 备注 |",
                "| --- | --- | --- |",
                "| 是否值得写 |  |  |",
                "| 是否符合48小时热点 |  |  |",
                "| 是否有趣/有梗/有传播潜力 |  |  |",
                "| 证据是否可信 |  |  |",
                "| 标题方向是否接近目标风格 |  |  |",
                "",
            ]
        )

    lines.extend(
        [
            "## 你的评价",
            "",
            "| 项目 | 你的选择或评分 | 备注 |",
            "| --- | --- | --- |",
            "| 本轮整体人工分(0-100) |  |  |",
            "| 风格方向 |  | 例如：更像游戏圈热帖 / 更像权威媒体简报 / 更像小红书故事化 |",
            "| 更应该奖励什么 |  | 例如：爆笑、争议、权威、玩家故事、硬件价格、流言准确率 |",
            "| 更应该惩罚什么 |  | 例如：旧闻、单源、无热度、标题党、无证据 |",
            "| 是否允许进入 Phase 5 |  | yes/no |",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"
