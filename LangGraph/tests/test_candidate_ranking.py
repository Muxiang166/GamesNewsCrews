from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from games_news_agent.ranking import filter_and_rank_candidates


def _candidate(
    title: str,
    *,
    hours_ago: int | None,
    source_id: str = "bilibili",
    heat_signals: dict | None = None,
    tags: list[str] | None = None,
) -> dict:
    now = datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
    observed_at = None if hours_ago is None else now - timedelta(hours=hours_ago)
    return {
        "title": title,
        "url": f"https://example.com/{title}",
        "source_id": source_id,
        "snippet": title,
        "query": "games",
        "discovered_at": now.isoformat(),
        "observed_at": observed_at.isoformat() if observed_at else None,
        "heat_signals": heat_signals or {},
        "tags": tags or [],
    }


class CandidateRankingTest(unittest.TestCase):
    def test_filters_candidates_to_configured_time_window(self) -> None:
        now = datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
        sources = {
            "bilibili": {"priority": 90, "kind": "community"},
        }
        candidates = [
            _candidate("玩家离谱操作被大量转载", hours_ago=2),
            _candidate("去年旧新闻复盘", hours_ago=72),
            _candidate("没有时间的线索", hours_ago=None),
        ]

        accepted, rejected = filter_and_rank_candidates(
            candidates,
            sources,
            now=now,
            lookback_hours=48,
        )

        self.assertEqual([item["title"] for item in accepted], ["玩家离谱操作被大量转载"])
        self.assertEqual({item["title"] for item in rejected}, {"去年旧新闻复盘", "没有时间的线索"})
        self.assertEqual(
            {item["reject_reason"] for item in rejected},
            {"outside_time_window", "missing_time"},
        )

    def test_high_heat_community_meme_outranks_low_heat_media_item(self) -> None:
        now = datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
        sources = {
            "bilibili": {"priority": 90, "kind": "community"},
            "ign": {"priority": 85, "kind": "media"},
        }
        candidates = [
            _candidate(
                "IGN 普通更新新闻",
                hours_ago=2,
                source_id="ign",
                heat_signals={"likes": 5, "comments": 1, "shares": 0},
                tags=["official_news"],
            ),
            _candidate(
                "微软游戏爆笑梗图被玩家刷屏",
                hours_ago=4,
                source_id="bilibili",
                heat_signals={"likes": 5000, "comments": 900, "shares": 1200},
                tags=["meme", "player_story", "hot_discussion"],
            ),
        ]

        accepted, rejected = filter_and_rank_candidates(
            candidates,
            sources,
            now=now,
            lookback_hours=48,
        )

        self.assertEqual(rejected, [])
        self.assertEqual(accepted[0]["title"], "微软游戏爆笑梗图被玩家刷屏")
        self.assertGreater(accepted[0]["heat_score"], accepted[1]["heat_score"])
        self.assertIn("community-source", accepted[0]["heat_reasons"])
        self.assertIn("meme/player-story", accepted[0]["heat_reasons"])

    def test_controversy_discussion_gets_specific_reason_not_meme_reason(self) -> None:
        now = datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
        sources = {
            "weibo": {"priority": 88, "kind": "community"},
        }
        candidates = [
            _candidate(
                "索尼 DEI 与亏损相关说法待核查",
                hours_ago=3,
                source_id="weibo",
                heat_signals={"likes": 2000, "comments": 1200, "reposts": 700},
                tags=["controversy", "dei", "loss", "hot_discussion"],
            )
        ]

        accepted, _ = filter_and_rank_candidates(
            candidates,
            sources,
            now=now,
            lookback_hours=48,
        )

        self.assertIn("hot-discussion", accepted[0]["heat_reasons"])
        self.assertIn("controversy-or-market-risk", accepted[0]["heat_reasons"])
        self.assertNotIn("meme/player-story", accepted[0]["heat_reasons"])

    def test_multi_platform_discussion_outranks_fresh_single_source_news(self) -> None:
        now = datetime(2026, 5, 11, 10, 0, tzinfo=timezone.utc)
        sources = {
            "ign": {"priority": 90, "kind": "media"},
            "gamersky": {"priority": 82, "kind": "media"},
        }
        candidates = [
            _candidate(
                "IGN 刚发布的普通预告片新闻",
                hours_ago=1,
                source_id="ign",
                heat_signals={},
                tags=["official_news"],
            ),
            _candidate(
                "Switch 2 涨价在微博 Reddit B站引发大量玩家热议",
                hours_ago=8,
                source_id="gamersky",
                heat_signals={},
                tags=["price"],
            ),
        ]

        accepted, _ = filter_and_rank_candidates(
            candidates,
            sources,
            now=now,
            lookback_hours=48,
        )

        self.assertEqual(accepted[0]["title"], "Switch 2 涨价在微博 Reddit B站引发大量玩家热议")
        self.assertGreater(accepted[0]["discussion_score"], accepted[1]["discussion_score"])
        self.assertIn("discussion:discussed", accepted[0]["heat_reasons"])


if __name__ == "__main__":
    unittest.main()
