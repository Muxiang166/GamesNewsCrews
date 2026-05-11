"""Game_News_Intelligence_System 项目入口。

负责：
- 读取 config/agents.yaml 与 config/tasks.yaml
- 组装 CrewAI 顺序流（Sequential Process）
- 使用 DuckDuckGoSearchRun 进行实时搜索
- 通过 DeepSeek（OpenAI 兼容接口）驱动各 Agent 产出最终 Markdown
"""

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv

from crewai import Agent, Crew, Process, Task
from crewai.tools import BaseTool
from langchain_community.tools import DuckDuckGoSearchRun
from pydantic import BaseModel, Field


class DuckDuckGoSearchToolInput(BaseModel):
    """DuckDuckGoSearchTool 的入参结构。"""

    query: str = Field(..., description="要在 DuckDuckGo 上搜索的查询语句")


class DuckDuckGoSearchTool(BaseTool):
    """CrewAI Tool：封装 LangChain 的 DuckDuckGoSearchRun。"""

    name: str = "DuckDuckGoSearchRun"
    description: str = (
        "使用 DuckDuckGo 进行实时网络搜索。输入 query，返回搜索结果文本。"
    )
    args_schema: type[BaseModel] = DuckDuckGoSearchToolInput

    def __init__(self) -> None:
        super().__init__()
        self._tool = DuckDuckGoSearchRun()

    def _run(self, *args: Any, **kwargs: Any) -> str:
        query = kwargs.get("query")
        if query is None and args:
            query = args[0]
        if not isinstance(query, str) or not query.strip():
            raise ValueError("DuckDuckGoSearchRun 需要非空的 query 参数")
        return self._tool.run(query)


@dataclass(frozen=True)
class AppConfig:
    """运行期配置（来自环境变量与命令行参数）。"""

    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    target_game: str
    search_time_range: str
    search_max_results: int


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"找不到配置文件：{path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件必须是 YAML mapping：{path}")
    return data


def _require_str_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"缺少环境变量：{name}")
    return value


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须是整数，当前值：{raw}") from exc


def _configure_llm_env(deepseek_api_key: str, deepseek_base_url: str) -> None:
    """
    CrewAI 通过 LiteLLM 对接多模型；DeepSeek 提供 OpenAI 兼容接口。
    这里将 DeepSeek 的配置映射为 LiteLLM/OpenAI 常用环境变量，减少额外依赖与配置复杂度。
    """
    os.environ.setdefault("OPENAI_API_KEY", deepseek_api_key)
    os.environ.setdefault("OPENAI_BASE_URL", deepseek_base_url)


def _load_app_config(args: argparse.Namespace) -> AppConfig:
    deepseek_api_key = _require_str_env("DEEPSEEK_API_KEY")
    deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").strip()
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

    target_game = (args.game or os.getenv("TARGET_GAME", "黑神话：悟空")).strip()
    search_time_range = (args.time_range or os.getenv("SEARCH_TIME_RANGE", "7d")).strip()
    search_max_results = (
        args.max_results
        if args.max_results is not None
        else _get_int_env("SEARCH_MAX_RESULTS", 20)
    )

    if search_max_results <= 0:
        raise ValueError("--max-results 必须是正整数")

    return AppConfig(
        deepseek_api_key=deepseek_api_key,
        deepseek_base_url=deepseek_base_url,
        deepseek_model=deepseek_model,
        target_game=target_game,
        search_time_range=search_time_range,
        search_max_results=search_max_results,
    )


def _apply_llm_to_agents_config(
    agents_config: Dict[str, Any],
    deepseek_model: str,
) -> None:
    model = f"openai/{deepseek_model}"
    for key, cfg in agents_config.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"agents.yaml 中 {key} 的配置必须是 mapping")
        cfg.setdefault("llm", model)


def _build_agents(
    agents_config: Dict[str, Any],
    deepseek_model: str,
) -> Dict[str, Agent]:
    _apply_llm_to_agents_config(agents_config, deepseek_model=deepseek_model)

    search_tool = DuckDuckGoSearchTool()

    agents: Dict[str, Agent] = {}
    for agent_key, cfg in agents_config.items():
        tools = [search_tool] if agent_key == "researcher" else []
        agent = Agent(
            config=cfg,
            verbose=True,
            allow_delegation=False,
            tools=tools,
        )
        agents[agent_key] = agent
    return agents


def _build_tasks(tasks_config: Dict[str, Any], agents: Dict[str, Agent]) -> list[Task]:
    tasks: list[Task] = []
    for task_key, cfg in tasks_config.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"tasks.yaml 中 {task_key} 的配置必须是 mapping")
        agent_key = cfg.get("agent")
        if not isinstance(agent_key, str) or not agent_key.strip():
            raise ValueError(f"tasks.yaml 中 {task_key} 缺少 agent 字段")
        if agent_key not in agents:
            raise ValueError(
                f"tasks.yaml 中 {task_key} 引用了不存在的 agent：{agent_key}"
            )

        description = cfg.get("description")
        expected_output = cfg.get("expected_output")
        output_file = cfg.get("output_file")

        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"tasks.yaml 中 {task_key} 缺少 description 字段")
        if not isinstance(expected_output, str) or not expected_output.strip():
            raise ValueError(f"tasks.yaml 中 {task_key} 缺少 expected_output 字段")
        if output_file is not None and not isinstance(output_file, str):
            raise ValueError(f"tasks.yaml 中 {task_key} 的 output_file 必须是字符串")

        tasks.append(
            Task(
                description=description,
                expected_output=expected_output,
                agent=agents[agent_key],
                output_file=output_file,
            )
        )
    return tasks


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="Game_News_Intelligence_System",
        description="多智能体游戏资讯情报系统（CrewAI 顺序流）",
    )
    parser.add_argument("--game", help="目标游戏名称（默认读取 TARGET_GAME）")
    parser.add_argument("--time-range", help="时间范围（例如 7d，默认读取 SEARCH_TIME_RANGE）")
    parser.add_argument(
        "--max-results",
        type=int,
        help="候选资讯条数（默认读取 SEARCH_MAX_RESULTS）",
    )
    return parser.parse_args(argv)


def main() -> int:
    """主入口：加载配置、组装 Crew、执行顺序流并输出结果。"""

    load_dotenv(override=False)

    try:
        args = _parse_args()
        app_cfg = _load_app_config(args)
        _configure_llm_env(app_cfg.deepseek_api_key, app_cfg.deepseek_base_url)

        outputs_dir = Path("outputs")
        outputs_dir.mkdir(parents=True, exist_ok=True)

        agents_cfg = _read_yaml(Path("config") / "agents.yaml")
        tasks_cfg = _read_yaml(Path("config") / "tasks.yaml")

        agents = _build_agents(agents_cfg, deepseek_model=app_cfg.deepseek_model)
        tasks = _build_tasks(tasks_cfg, agents)

        crew = Crew(
            agents=list(agents.values()),
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

        inputs = {
            "game": app_cfg.target_game,
            "time_range": app_cfg.search_time_range,
            "max_results": app_cfg.search_max_results,
            "current_year": datetime.now().year,
        }

        result = crew.kickoff(inputs=inputs)
        print("\n=== Crew Finished ===")
        print(getattr(result, "raw", str(result)))
        print("\nOutputs directory:", outputs_dir.resolve())
        return 0
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

