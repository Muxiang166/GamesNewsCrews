"""Minimal HTTP text fetching for live collectors."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class FetchResult:
    url: str
    ok: bool
    status_code: int | None = None
    content_type: str = ""
    text: str = ""
    error: str = ""
    error_type: str = ""
    retryable: bool = False
    attempts: list[dict[str, Any]] = field(default_factory=list)


OpenUrl = Callable[..., Any]
Sleep = Callable[[float], None]


def _content_type(headers: Any) -> str:
    if headers is None:
        return ""
    if hasattr(headers, "get"):
        return str(headers.get("content-type") or headers.get("Content-Type") or "")
    return ""


def _header_charset(headers: Any) -> str:
    if headers is not None and hasattr(headers, "get_content_charset"):
        charset = headers.get_content_charset()
        if charset:
            return str(charset)

    content_type = _content_type(headers)
    match = re.search(r"charset=[\"']?([^\"';\s]+)", content_type, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def _meta_charset(body: bytes) -> str:
    head = body[:4096].decode("ascii", errors="ignore")
    match = re.search(r"charset=[\"']?([^\"'>;\s]+)", head, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def _decode_body(body: bytes, headers: Any) -> str:
    candidates = [_header_charset(headers), _meta_charset(body), "utf-8", "gb18030"]
    seen: set[str] = set()
    for charset in candidates:
        normalized = charset.strip().strip('"').strip("'").lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            return body.decode(normalized)
        except (LookupError, UnicodeDecodeError):
            continue

    return body.decode("utf-8", errors="replace")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _retry_after_seconds(headers: Any) -> float | None:
    if headers is None or not hasattr(headers, "get"):
        return None
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(float(str(value).strip()), 0.0)
    except ValueError:
        return None


def _http_error_type(status_code: int | None) -> str:
    return f"http_{status_code}" if status_code is not None else "http_error"


def _http_status_retryable(status_code: int | None) -> bool:
    if status_code is None:
        return False
    return status_code == 429 or 500 <= status_code <= 599


def _cooldown_until(sleep_seconds: float) -> str:
    if sleep_seconds <= 0:
        return ""
    return (datetime.now(timezone.utc) + timedelta(seconds=sleep_seconds)).isoformat()


class HttpFetcher:
    """Small stdlib fetcher with dependency injection for tests."""

    def __init__(
        self,
        *,
        timeout: float = 12.0,
        user_agent: str | None = None,
        open_url: OpenUrl | None = None,
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
        backoff_max_seconds: float = 8.0,
        sleep: Sleep | None = None,
    ) -> None:
        self.timeout = timeout
        self.user_agent = (
            user_agent
            or os.environ.get("GAMES_NEWS_USER_AGENT")
            or "GamesNewsAgent/0.1"
        )
        self.open_url = open_url or urlopen
        self.max_attempts = max(int(max_attempts), 1)
        self.backoff_base_seconds = max(float(backoff_base_seconds), 0.0)
        self.backoff_max_seconds = max(float(backoff_max_seconds), 0.0)
        self.sleep = sleep or time.sleep

    def _sleep_seconds(self, attempt_index: int, headers: Any = None) -> float:
        retry_after = _retry_after_seconds(headers)
        if retry_after is not None:
            return retry_after
        if self.backoff_base_seconds <= 0:
            return 0.0
        return min(
            self.backoff_base_seconds * (2 ** max(attempt_index - 1, 0)),
            self.backoff_max_seconds,
        )

    def _attempt_record(
        self,
        *,
        attempt_index: int,
        started_at: str,
        ended_at: str,
        ok: bool,
        status_code: int | None = None,
        error: str = "",
        error_type: str = "",
        retryable: bool = False,
        will_retry: bool = False,
        sleep_seconds: float = 0.0,
    ) -> dict[str, Any]:
        return {
            "attempt_index": attempt_index,
            "started_at": started_at,
            "ended_at": ended_at,
            "ok": ok,
            "status_code": status_code,
            "error": error,
            "error_type": error_type,
            "retryable": retryable,
            "will_retry": will_retry,
            "sleep_seconds": sleep_seconds,
            "cooldown_until": _cooldown_until(sleep_seconds),
        }

    def fetch_text(self, url: str, *, timeout: float | None = None) -> FetchResult:
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
            },
        )
        effective_timeout = self.timeout if timeout is None else timeout
        attempts: list[dict[str, Any]] = []

        for attempt_index in range(1, self.max_attempts + 1):
            started_at = _utc_now_iso()
            try:
                with self.open_url(request, timeout=effective_timeout) as response:
                    headers = getattr(response, "headers", None)
                    body = response.read()
                    status_code = (
                        getattr(response, "status", None)
                        or getattr(response, "code", None)
                        or response.getcode()
                    )
                    attempts.append(
                        self._attempt_record(
                            attempt_index=attempt_index,
                            started_at=started_at,
                            ended_at=_utc_now_iso(),
                            ok=True,
                            status_code=status_code,
                        )
                    )
                    return FetchResult(
                        url=url,
                        ok=True,
                        status_code=status_code,
                        content_type=_content_type(headers),
                        text=_decode_body(body, headers),
                        attempts=attempts,
                    )
            except HTTPError as exc:
                headers = getattr(exc, "headers", None)
                body = exc.read() if hasattr(exc, "read") else b""
                status_code = exc.code
                error_type = _http_error_type(status_code)
                retryable = _http_status_retryable(status_code)
                will_retry = retryable and attempt_index < self.max_attempts
                sleep_seconds = self._sleep_seconds(attempt_index, headers) if will_retry else 0.0
                attempts.append(
                    self._attempt_record(
                        attempt_index=attempt_index,
                        started_at=started_at,
                        ended_at=_utc_now_iso(),
                        ok=False,
                        status_code=status_code,
                        error=str(exc),
                        error_type=error_type,
                        retryable=retryable,
                        will_retry=will_retry,
                        sleep_seconds=sleep_seconds,
                    )
                )
                if will_retry:
                    self.sleep(sleep_seconds)
                    continue
                return FetchResult(
                    url=url,
                    ok=False,
                    status_code=status_code,
                    content_type=_content_type(headers),
                    text=_decode_body(body, headers),
                    error=str(exc),
                    error_type=error_type,
                    retryable=retryable,
                    attempts=attempts,
                )
            except URLError as exc:
                error = str(exc.reason)
                retryable = True
                will_retry = attempt_index < self.max_attempts
                sleep_seconds = self._sleep_seconds(attempt_index) if will_retry else 0.0
                attempts.append(
                    self._attempt_record(
                        attempt_index=attempt_index,
                        started_at=started_at,
                        ended_at=_utc_now_iso(),
                        ok=False,
                        error=error,
                        error_type="url_error",
                        retryable=retryable,
                        will_retry=will_retry,
                        sleep_seconds=sleep_seconds,
                    )
                )
                if will_retry:
                    self.sleep(sleep_seconds)
                    continue
                return FetchResult(
                    url=url,
                    ok=False,
                    error=error,
                    error_type="url_error",
                    retryable=retryable,
                    attempts=attempts,
                )
            except OSError as exc:
                error = str(exc)
                retryable = True
                will_retry = attempt_index < self.max_attempts
                sleep_seconds = self._sleep_seconds(attempt_index) if will_retry else 0.0
                attempts.append(
                    self._attempt_record(
                        attempt_index=attempt_index,
                        started_at=started_at,
                        ended_at=_utc_now_iso(),
                        ok=False,
                        error=error,
                        error_type="os_error",
                        retryable=retryable,
                        will_retry=will_retry,
                        sleep_seconds=sleep_seconds,
                    )
                )
                if will_retry:
                    self.sleep(sleep_seconds)
                    continue
                return FetchResult(
                    url=url,
                    ok=False,
                    error=error,
                    error_type="os_error",
                    retryable=retryable,
                    attempts=attempts,
                )

        return FetchResult(url=url, ok=False, error="fetch_attempts_exhausted", attempts=attempts)
