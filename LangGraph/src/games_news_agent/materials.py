"""Material bundle builders for human content validation.

This module keeps article assets, evidence quotes, story sources, and review
entrypoints together so a live run can be judged before layout rendering.
"""

from __future__ import annotations

from typing import Any, Iterable


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    results: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            results.append(text)
    return results


def _short_text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            results.append(value)
    return results


def build_assets_from_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert fetched document image URLs into traceable article assets."""

    assets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for document_index, document in enumerate(documents):
        if not isinstance(document, dict):
            continue
        source_url = str(document.get("candidate_url") or document.get("url") or "").strip()
        source_id = str(document.get("source_id") or "").strip()
        title = str(document.get("title") or "").strip()
        for image_url in _string_list(document.get("image_urls")):
            key = (source_url, image_url)
            if key in seen:
                continue
            seen.add(key)
            assets.append(
                {
                    "id": f"asset_{len(assets) + 1:03d}",
                    "url": image_url,
                    "kind": "article_image",
                    "source_url": source_url,
                    "source_id": source_id,
                    "title": title,
                    "status": "available",
                    "note": "",
                    "metadata": {"document_index": document_index},
                }
            )
    return assets


def _evidence_quotes(claims: list[dict[str, Any]]) -> list[str]:
    quotes: list[str] = []
    for claim in claims:
        evidence_items = claim.get("evidence", [])
        if not isinstance(evidence_items, list):
            continue
        for evidence in evidence_items:
            if isinstance(evidence, dict):
                quote = _short_text(evidence.get("quote"))
                if quote:
                    quotes.append(quote)
    return _unique(quotes)[:3]


def _story_assets(
    story: dict[str, Any],
    assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_urls = set(_string_list(story.get("source_urls")))
    if not source_urls:
        return []
    return [
        asset
        for asset in assets
        if isinstance(asset, dict)
        and str(asset.get("source_url") or "").strip() in source_urls
        and asset.get("status") == "available"
    ]


def _platform_posts_for_story(
    story_id: str,
    platform_posts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        post
        for post in platform_posts
        if isinstance(post, dict) and str(post.get("story_id") or "") == story_id
    ]


def attach_assets_to_stories(
    stories: list[dict[str, Any]],
    assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return story copies with available assets matched by source URL."""

    enriched: list[dict[str, Any]] = []
    for story in stories:
        if not isinstance(story, dict):
            continue
        story_copy = dict(story)
        existing_assets = [
            asset for asset in story_copy.get("assets", []) if isinstance(asset, dict)
        ]
        matched_assets = _story_assets(story_copy, assets)
        seen = {
            (
                str(asset.get("source_url") or ""),
                str(asset.get("url") or ""),
            )
            for asset in existing_assets
        }
        for asset in matched_assets:
            key = (str(asset.get("source_url") or ""), str(asset.get("url") or ""))
            if key not in seen:
                existing_assets.append(asset)
                seen.add(key)
        story_copy["assets"] = existing_assets
        enriched.append(story_copy)
    return enriched


def build_material_bundle(state: dict[str, Any]) -> dict[str, Any]:
    """Build a review-first material package from the current pipeline state."""

    quality_report = state.get("content_quality_report", {})
    if not isinstance(quality_report, dict):
        quality_report = {}

    assets = [item for item in state.get("assets", []) if isinstance(item, dict)]
    stories = [item for item in state.get("stories", []) if isinstance(item, dict)]
    platform_posts = [item for item in state.get("platform_posts", []) if isinstance(item, dict)]

    story_materials: list[dict[str, Any]] = []
    missing_story_assets = 0
    for story in stories:
        story_id = str(story.get("id") or "").strip()
        source_urls = _string_list(story.get("source_urls"))
        claims = [claim for claim in story.get("claims", []) if isinstance(claim, dict)]
        matched_assets = _story_assets(story, assets)
        asset_status = "available" if matched_assets else "manual_fill_required"
        if asset_status == "manual_fill_required":
            missing_story_assets += 1
        story_materials.append(
            {
                "story_id": story_id,
                "title": str(story.get("title") or ""),
                "status": str(story.get("status") or ""),
                "category": str(story.get("category") or ""),
                "story_score": story.get("story_score"),
                "source_urls": source_urls,
                "evidence_quotes": _evidence_quotes(claims),
                "assets": matched_assets,
                "asset_status": asset_status,
                "asset_note": ""
                if matched_assets
                else "No article image was extracted; leave layout slot empty or fill manually after review.",
                "platform_posts": _platform_posts_for_story(story_id, platform_posts),
                "review_fields": {
                    "human_score": "",
                    "style_direction": "",
                    "asset_notes": "",
                    "publish_decision": "",
                },
            }
        )

    return {
        "version": "0.1.0",
        "status": str(
            quality_report.get("gate_status")
            or quality_report.get("readiness")
            or "unscored"
        ),
        "summary": {
            "candidates": len(state.get("candidates", [])),
            "documents": len(state.get("documents", [])),
            "stories": len(stories),
            "platform_posts": len(platform_posts),
            "assets": len(assets),
            "available_assets": sum(1 for asset in assets if asset.get("status") == "available"),
            "missing_story_assets": missing_story_assets,
            "overall_score": quality_report.get("overall_score"),
        },
        "assets": assets,
        "story_materials": story_materials,
        "review_paths": {
            "content_review": state.get("content_review_path", ""),
            "human_review_template": state.get("human_review_template_path", ""),
            "content_quality_report": state.get("content_quality_report_path", ""),
        },
    }
