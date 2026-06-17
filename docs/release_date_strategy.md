# 游戏发售日期更新策略

本文记录 `GameReleaseCalendar` 的目标、边界和落地顺序。它服务于新闻筛选、发售提醒、历史背景、延期追踪和“本周发售/那年今日”内容，不替代新闻事实核查。

## 目标

- 从入选 story、主题候选池和人工指定游戏中识别游戏实体。
- 更新每个游戏在不同平台、地区、版本上的发售日期。
- 记录日期变更事件，而不是只保存最新值。
- 为 `HistoricalContextMiner`、`RAG QA`、内容质量评分和未来内容运营提供结构化事实。

## 非目标

- 不全量爬取所有游戏数据库。
- 不把社交平台讨论当作发售日期事实。
- 不让 LLM 无来源补日期。
- 不在 Phase 4.5 之前把发售日板块强行纳入最终 Top 10。

## 数据结构

### GameReleaseRecord

```json
{
  "game_id": "game_hollow_knight_silksong",
  "canonical_title": "Hollow Knight: Silksong",
  "aliases": ["丝之歌", "空洞骑士 丝之歌"],
  "series": "Hollow Knight",
  "publisher": "Team Cherry",
  "developer": "Team Cherry",
  "platforms": ["pc", "switch", "playstation", "xbox"],
  "regions": ["global"],
  "release_dates": [
    {
      "platform": "pc",
      "region": "global",
      "edition": "standard",
      "date_text": "2026-09-04",
      "date_precision": "exact_date",
      "date_status": "announced",
      "source_urls": ["https://example.invalid/official"],
      "confidence": 0.95
    }
  ],
  "last_checked_at": "2026-06-14T00:00:00+08:00"
}
```

### ReleaseDateChangeEvent

```json
{
  "change_id": "release_change_0001",
  "game_id": "game_hollow_knight_silksong",
  "change_type": "date_changed",
  "platform": "pc",
  "region": "global",
  "old_value": "2026",
  "new_value": "2026-09-04",
  "old_precision": "year_window",
  "new_precision": "exact_date",
  "source_urls": ["https://example.invalid/official"],
  "detected_at": "2026-06-14T00:00:00+08:00",
  "confidence": 0.9,
  "review_status": "auto_accept"
}
```

## 来源优先级

1. 官方与平台商店：开发商/发行商官网、Steam、PlayStation Store、Xbox Store、Nintendo eShop、Epic、GOG。
2. 官方新闻物料：press release、官方博客、官方视频简介、发布会页面、邮件新闻稿。
3. 权威媒体：IGN、GameSpot、PC Gamer、游民星空等，用于补充官方未结构化信息。
4. 游戏数据库/API：IGDB、RAWG、Steam API 等，用于批量补全和别名映射，接入前检查授权与字段粒度。
5. 社交平台：只作为发售/延期讨论热度线索，不写入高置信度日期事实。

## 更新流程

```text
Story/Candidate
 -> GameIdentityResolver
 -> ReleaseDateCollector
 -> ReleaseDateNormalizer
 -> ReleaseDateComparator
 -> ReleaseDateChangeClassifier
 -> ReleaseCalendarReviewer
 -> GameReleaseCalendarStore
```

## 变更类型

- `new_game_added`：新游戏进入日历。
- `date_confirmed`：模糊窗口变成明确日期。
- `date_changed`：发售日从一个明确值改为另一个明确值。
- `delayed`：延期或从明确日期退回窗口/TBD。
- `advanced`：提前发售或提前解锁。
- `platform_added`：新增平台版本。
- `region_added`：新增地区版本。
- `released_today`：确认已发售或突然上架。
- `removed_or_uncertain`：商店页下架、日期消失或来源冲突。

## LLM/Agent 边界

LLM 适合：

- 把自然语言日期归一化成结构化 JSON。
- 判断“豪华版提前解锁”“抢先体验”“正式版”“DLC”是否是同一发行节点。
- 在冲突证据中生成人工复核摘要。

LLM 不适合：

- 凭空补日期。
- 新增没有来源的游戏实体。
- 把社交讨论当官方改期。
- 自动覆盖高置信度官方记录。

## MVP 顺序

1. 只从 `stories.json` 和 `theme_candidate_pool.json` 抽取 Top N 游戏实体。
2. 先实现 `game_release_records.json` 和 `release_date_changes.json` 的 artifact contract。
3. 先用 fixture/harness 测试日期精度、平台/地区拆分和变更分类。
4. 接入 Steam/官方页面/权威媒体的低频 collector。
5. 生成 `release_calendar_review.md` 供人工确认冲突和低置信度记录。
6. 稳定后再接 SQLite/FTS 与 RAG-2 历史记忆。

