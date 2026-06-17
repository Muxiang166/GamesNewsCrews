# Long-Lookback Evaluation Guide

Use 30-day and 60-day runs to evaluate post-collection ranking, backfill and event-burst behavior. Do not use these runs as daily briefing output.

## 30-Day Collection

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 720 --topic games --document-fetch-limit 20 --theme-candidate-pool-limit 300 --run-selection-backfill --selection-backfill-limit 30 --output-dir outputs\langgraph\eval_30d_collection --memory-path outputs\langgraph\memory\eval_30d_candidate_memory.json
```

## 60-Day Collection

```powershell
D:\Anaconda\envs\gamesnewscrew\python.exe LangGraph\main.py --lookback-hours 1440 --topic games --document-fetch-limit 30 --theme-candidate-pool-limit 500 --run-selection-backfill --selection-backfill-limit 50 --output-dir outputs\langgraph\eval_60d_collection --memory-path outputs\langgraph\memory\eval_60d_candidate_memory.json
```

## Review Checklist

- Compare `source_theme_counts.json` with `theme_candidate_pool.json`.
- Compare `theme_candidate_pool.sections[].fetch_selected_count` with `story_candidates.json`.
- Treat `--document-fetch-limit` as a per-section budget. For example, `20` means up to 20 Sony, 20 Nintendo, 20 Microsoft, 20 PC and 20 supplemental candidates.
- Check `selection_stage_diagnostics.json` for the main bottleneck in each theme section.
- Check `selection_backfill_candidates.json` to see whether underfilled sections have useful second-pass candidates.
- Check whether event-burst days produce enough Nintendo/Sony/Microsoft/PC story candidates.
- Check whether old news, late reposts and current follow-up updates are separated correctly.
- Check whether core game news is being displaced by repeated sentiment topics such as "console left unused" discussions.
