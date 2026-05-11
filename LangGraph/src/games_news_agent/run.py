"""CLI entry point for the LangGraph skeleton."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from .graph import build_graph
from .schemas import PipelineState


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="games-news-agent",
        description="Run the LangGraph games news intelligence skeleton.",
    )
    parser.add_argument("--topic", default="games", help="Topic seed for the run.")
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=48,
        help="Hard recency window for future collectors.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/langgraph/latest",
        help="Directory for generated artifacts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without live search/fetch collectors.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(override=False)
    args = parse_args(argv)

    if args.lookback_hours <= 0:
        raise ValueError("--lookback-hours must be positive")

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    initial_state: PipelineState = {
        "topic": args.topic,
        "dry_run": args.dry_run,
        "lookback_hours": args.lookback_hours,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": args.output_dir,
        "notes": [],
    }

    app = build_graph()
    final_state = app.invoke(initial_state)

    print("LangGraph skeleton run finished.")
    print(f"Briefing: {final_state.get('briefing_path')}")
    print(f"Layout manifest: {final_state.get('layout_manifest_path')}")
    print(f"Render queue: {final_state.get('render_queue_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
