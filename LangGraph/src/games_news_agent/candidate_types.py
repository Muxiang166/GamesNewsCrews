"""Candidate type classification and main/supplemental lane splitting."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


CandidateLane = Literal["main", "supplemental"]


@dataclass(frozen=True)
class CandidateTypeResult:
    candidate_type: str
    candidate_lane: CandidateLane
    reasons: list[str]


def _haystack(candidate: dict[str, Any]) -> str:
    tags = " ".join(str(tag) for tag in candidate.get("tags", []))
    parts = [
        candidate.get("title", ""),
        candidate.get("snippet", ""),
        candidate.get("url", ""),
        tags,
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _result(candidate_type: str, lane: CandidateLane, *reasons: str) -> CandidateTypeResult:
    return CandidateTypeResult(candidate_type, lane, [reason for reason in reasons if reason])


GAME_SIGNAL_PATTERN = (
    r"\b(game|games|gaming|xbox|playstation|ps5|ps6|nintendo|switch|steam|forza|"
    r"subnautica|gta|grand theft auto|marathon|overwatch|diablo|pokemon|final fantasy|"
    r"stardew|doom|warhammer|bioware|rpg|mmo|pve|controller|console|batman|lego)\b|"
    r"游戏|玩家|主机|索尼|微软|任天堂|英雄联盟|荒野大镖客|鸣潮|羊蹄山|深海迷航|乐高蝙蝠侠|最终幻想|ns2"
)
GUIDE_PATTERN = (
    r"\b(how to|where to|guide|walkthrough|tips|console commands|settings|locations|"
    r"find all|craft|activate|increase inventory|food and water|oxygen|silver|lithium|"
    r"quartz|acid|scanner upgrade)\b|攻略|流程|指南|教程|点位|全任务|图文流程|如何获取"
)
DEAL_PATTERN = (
    r"\b(deal|deals|sale|% off|drops to|free delivery|best nintendo deals|"
    r"preorder these upcoming|preorder .* deals|discount|50% off)\b|"
    r"入手更划算|价格永降|预售：|降价 新机|大降价"
)
GENERAL_TECH_PATTERN = (
    r"\b(iphone|apple watch|electric bike|oled tv|bitcoin|ai servers|graduate speaker|"
    r"ddr4|memory module|copper was king|pc enthusiasts|rog anniversary)\b|"
    r"苹果手机|iphone|三星lg|小米耳机|内存暴涨|华强北|电动自行车"
)
MEME_GALLERY_PATTERN = r"囧图|美女|女孩|美白|大就是美"
OFF_TOPIC_ENTERTAINMENT_PATTERN = (
    r"网红|明星|帅哥|富豪|男友|女友|暧昧|小三|恋情|约会|八卦|绯闻|"
    r"社会新闻|市监局|鹅腿阿姨|滨崎步|易梦玲|胖东来|于东来|流行天后|梅西.*表情包|"
    r"比尔盖茨.*(爱泼斯坦|出轨|勒索)|爱泼斯坦.*比尔盖茨|"
    r"黄仁勋.*(皮夹克|满头大汗|冒汗|韩国)|"
    r"\bcelebrity|influencer|dating|boyfriend|girlfriend\b"
)
STRONG_RUMOR_PATTERN = (
    r"\b(leak|leaks|leaked|rumor|says preorders begin|may be announced|may begin)\b|"
    r"爆料称|爆料|传闻|据称|有望|泄露"
)
WEAK_EXPOSURE_PATTERN = r"\b(reportedly)\b|曝光|曝"
CONFIRMED_REPORT_PATTERN = (
    r"已上线|正式上线|推送上线|新增|公开|公布|发布|发售日|定档|"
    r"报道|采访|主创谈及|团队表示|开发团队表示|深入.*工作室|系统版本"
)
PLATFORM_PRICE_PATTERN = (
    r"\b(price|prices|pricing|preorders begin|stock price|pricing themselves out)\b|"
    r"涨价|定价|售价|亏本|销量|首周|价格"
)
REVIEW_SCORE_PATTERN = (
    r"\b(metacritic|opencritic|review score|reviews? returned|scored|score)\b|"
    r"m站|媒体评分|评分解禁|斩获.*分|获得.*分|高分|低分|差评|好评"
)
RELEASE_OR_UPDATE_PATTERN = (
    r"\b(release time|release times|full release|early access|launch|preload|go live|"
    r"festival playlist|patch|update|revealed|confirmed)\b|"
    r"发售|解锁|预载|上线|更新|公布|确认|定档|新增"
)
COMMUNITY_DEBATE_PATTERN = (
    r"热议|争议|走红|疯传|转发|玩家|客服|补偿|梗|整活|离谱|无厘头|投票|评论区|"
    r"\bhot topic|debate|community|fans\b"
)
PC_HARDWARE_EVENT_PATTERN = (
    r"微星|京东mall|线下观赛|外设体验|rtx\s*\d+|geforce|nvidia|amd|显卡|外设|硬件活动|"
    r"\bmsi|geforce|rtx|nvidia|pc hardware\b"
)
PLATFORM_HARDWARE_PATTERN = (
    r"\b(xbox|playstation|ps5|ps6|nintendo|switch|steam machine|steam controller|"
    r"controller|console|gpu|amd gpu|nvidia|pssr|xsx|pc gaming hardware|alienware)\b|"
    r"主机|掌机|手柄|xsx|ps5|ps6|switch|任天堂|索尼|微软|ns2"
)


def classify_candidate_type(candidate: dict[str, Any]) -> CandidateTypeResult:
    text = _haystack(candidate)
    has_game_signal = _has(GAME_SIGNAL_PATTERN, text)

    if _has(OFF_TOPIC_ENTERTAINMENT_PATTERN, text):
        return _result("off_topic_entertainment", "supplemental", "celebrity_or_gossip")

    if _has(MEME_GALLERY_PATTERN, text):
        return _result("meme_gallery", "supplemental", "gallery_or_light_meme")

    if _has(GUIDE_PATTERN, text):
        return _result("guide", "supplemental", "guide_or_walkthrough")

    if _has(GENERAL_TECH_PATTERN, text) and not _has(PLATFORM_HARDWARE_PATTERN, text):
        return _result("general_tech", "supplemental", "generic_tech_without_game_platform")

    if _has(PC_HARDWARE_EVENT_PATTERN, text) and not _has(r"steam machine|xbox|playstation|ps5|ps6|switch|主机|掌机|手柄|索尼|微软|任天堂|ns2", text):
        return _result("pc_hardware_or_event", "supplemental", "pc_hardware_event_not_core_console_or_game_news")

    if _has(DEAL_PATTERN, text) and not _has(PLATFORM_PRICE_PATTERN, text):
        return _result("deal", "supplemental", "shopping_or_discount")

    has_confirmed_report = _has(CONFIRMED_REPORT_PATTERN, text)
    has_strong_rumor = _has(STRONG_RUMOR_PATTERN, text)
    has_weak_exposure = _has(WEAK_EXPOSURE_PATTERN, text)

    if has_strong_rumor and has_game_signal and not ("已上线" in text or "推送上线" in text):
        return _result("rumor", "main", "game_rumor_or_leak")

    if _has(REVIEW_SCORE_PATTERN, text) and has_game_signal:
        return _result("review_score", "main", "game_review_score")

    if has_confirmed_report and has_game_signal:
        return _result("news", "main", "reported_or_live_game_news")

    if has_weak_exposure and has_game_signal and not has_confirmed_report:
        return _result("rumor", "main", "game_rumor_or_leak")

    if _has(PLATFORM_PRICE_PATTERN, text) and has_game_signal:
        return _result("platform_price", "main", "platform_or_market_price")

    if _has(PLATFORM_HARDWARE_PATTERN, text) and has_game_signal:
        return _result("hardware_platform", "main", "game_platform_hardware")

    if _has(RELEASE_OR_UPDATE_PATTERN, text) and has_game_signal:
        return _result("news", "main", "game_release_or_update")

    if _has(COMMUNITY_DEBATE_PATTERN, text) and has_game_signal:
        return _result("news", "main", "community_debate_or_player_story")

    if _has(DEAL_PATTERN, text):
        return _result("deal", "supplemental", "shopping_or_discount")

    if _has(GENERAL_TECH_PATTERN, text):
        return _result("general_tech", "supplemental", "generic_tech")

    return _result("manual_review", "supplemental", "missing_editorial_focus")


def annotate_candidate_type(candidate: dict[str, Any]) -> dict[str, Any]:
    classification = classify_candidate_type(candidate)
    annotated = dict(candidate)
    annotated["candidate_type"] = classification.candidate_type
    annotated["candidate_lane"] = classification.candidate_lane
    annotated["candidate_type_reasons"] = classification.reasons
    return annotated


def split_candidate_lanes(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    main: list[dict[str, Any]] = []
    supplemental: list[dict[str, Any]] = []
    for candidate in candidates:
        annotated = annotate_candidate_type(candidate)
        if annotated["candidate_lane"] == "supplemental":
            supplemental.append(annotated)
        else:
            main.append(annotated)
    return main, supplemental
