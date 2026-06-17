"""Local IDE entry point for the LangGraph games news agent."""

from __future__ import annotations

import sys
from pathlib import Path


LANGGRAPH_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = LANGGRAPH_ROOT.parent
SRC_ROOT = LANGGRAPH_ROOT / "src"
from games_news_agent.run import main  # noqa: E402
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))




def _default_args() -> list[str]:
    return [
        "--lookback-hours",
        "48",
        "--topic",
        "games",
        "--output-dir",
        str(PROJECT_ROOT / "outputs" / "langgraph" / "live_test"),
    ]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or _default_args()))
