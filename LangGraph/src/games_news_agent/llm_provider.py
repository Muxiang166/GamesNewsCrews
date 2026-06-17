"""OpenAI-compatible LLM provider for verification requests."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .llm_verifier import parse_llm_verification_response


OpenUrl = Callable[..., Any]


@dataclass(frozen=True)
class LlmConfig:
    api_key: str
    base_url: str
    model: str
    timeout: float = 45.0
    temperature: float = 0.1
    max_tokens: int = 700


def load_llm_config(env: Mapping[str, str] | None = None) -> LlmConfig:
    values = env or os.environ
    api_key = (
        values.get("DEEPSEEK_API_KEY")
        or values.get("LLM_API_KEY")
        or values.get("OPENAI_API_KEY")
        or ""
    ).strip()
    base_url = (
        values.get("DEEPSEEK_BASE_URL")
        or values.get("LLM_BASE_URL")
        or values.get("OPENAI_BASE_URL")
        or "https://api.deepseek.com/v1"
    ).strip()
    model = (
        values.get("DEEPSEEK_MODEL")
        or values.get("LLM_MODEL")
        or values.get("OPENAI_MODEL")
        or "deepseek-chat"
    ).strip()
    timeout = float(values.get("LLM_TIMEOUT", "45"))
    temperature = float(values.get("LLM_TEMPERATURE", "0.1"))
    max_tokens = int(values.get("LLM_MAX_TOKENS", "700"))
    return LlmConfig(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        model=model,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _chat_completion_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _messages_for_request(request: dict[str, Any]) -> list[dict[str, str]]:
    user_payload = {
        "claim": request.get("claim", {}),
        "evidence": request.get("evidence", []),
        "allowed_statuses": request.get("allowed_statuses", []),
        "json_schema": request.get("json_schema", {}),
    }
    return [
        {
            "role": "system",
            "content": str(request.get("instructions", "Return JSON only.")),
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False),
        },
    ]


def _messages_for_json_request(request: dict[str, Any]) -> list[dict[str, str]]:
    user_payload = {
        key: value
        for key, value in request.items()
        if key not in {"instructions"}
    }
    return [
        {
            "role": "system",
            "content": str(request.get("instructions", "Return JSON only.")),
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False),
        },
    ]


def _provider_error_result(request_id: str, error: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "parse_status": "provider_error",
        "check_status": "manual_review_required",
        "confidence": 0.0,
        "rationale": error,
        "used_evidence_chunk_ids": [],
        "risk_flags": ["llm_provider_error"],
    }


def _provider_error_json_result(request_id: str, error: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "parse_status": "provider_error",
        "error": error,
        "content": "",
        "usage": {},
    }


class OpenAICompatibleVerifierClient:
    def __init__(
        self,
        config: LlmConfig,
        *,
        open_url: OpenUrl | None = None,
    ) -> None:
        self.config = config
        self.open_url = open_url or urlopen

    def verify_request(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = str(request.get("request_id", ""))
        if not self.config.api_key:
            return _provider_error_result(request_id, "missing_api_key")

        payload = {
            "model": self.config.model,
            "messages": _messages_for_request(request),
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        http_request = Request(
            _chat_completion_url(self.config.base_url),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with self.open_url(http_request, timeout=self.config.timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            return _provider_error_result(request_id, f"HTTP {exc.code}: {body}")
        except (OSError, URLError, json.JSONDecodeError) as exc:
            return _provider_error_result(request_id, str(exc))

        choices = response_payload.get("choices", [])
        if not choices:
            return _provider_error_result(request_id, "missing_choices")
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        content = str(message.get("content", ""))
        parsed = parse_llm_verification_response(request_id, content)
        parsed["usage"] = response_payload.get("usage", {})
        parsed["model"] = response_payload.get("model", self.config.model)
        return parsed


def run_llm_verification_requests(
    requests: list[dict[str, Any]],
    *,
    config: LlmConfig | None = None,
    limit: int | None = None,
    open_url: OpenUrl | None = None,
) -> list[dict[str, Any]]:
    effective_config = config or load_llm_config()
    client = OpenAICompatibleVerifierClient(effective_config, open_url=open_url)
    selected = requests if limit is None else requests[: max(limit, 0)]
    return [client.verify_request(request) for request in selected]


def run_llm_json_requests(
    requests: list[dict[str, Any]],
    *,
    config: LlmConfig | None = None,
    limit: int | None = None,
    open_url: OpenUrl | None = None,
) -> list[dict[str, Any]]:
    effective_config = config or load_llm_config()
    selected = requests if limit is None else requests[: max(limit, 0)]
    opener = open_url or urlopen
    results: list[dict[str, Any]] = []
    for request in selected:
        request_id = str(request.get("request_id", ""))
        if not effective_config.api_key:
            results.append(_provider_error_json_result(request_id, "missing_api_key"))
            continue
        payload = {
            "model": effective_config.model,
            "messages": _messages_for_json_request(request),
            "temperature": effective_config.temperature,
            "max_tokens": effective_config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        http_request = Request(
            _chat_completion_url(effective_config.base_url),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {effective_config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with opener(http_request, timeout=effective_config.timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
            results.append(_provider_error_json_result(request_id, f"HTTP {exc.code}: {body}"))
            continue
        except (OSError, URLError, json.JSONDecodeError) as exc:
            results.append(_provider_error_json_result(request_id, str(exc)))
            continue

        choices = response_payload.get("choices", [])
        if not choices:
            results.append(_provider_error_json_result(request_id, "missing_choices"))
            continue
        message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
        results.append(
            {
                "request_id": request_id,
                "parse_status": "ok",
                "content": str(message.get("content", "")),
                "usage": response_payload.get("usage", {}),
                "model": response_payload.get("model", effective_config.model),
            }
        )
    return results
