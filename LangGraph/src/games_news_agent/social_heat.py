"""Social heat observation contracts.

This module does not fetch social platforms. It normalizes observations from
public search, manual import, browser sidecars, or future APIs into one shape so
downstream ranking can audit heat evidence without caring how it was collected.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

# ---------------------------------------------------------------------------
# SocialHeatProviderContract (HEAT-001)
# ---------------------------------------------------------------------------

AccessMethod = Literal["public_search", "api", "browser_sidecar", "manual_import"]


class SocialHeatProviderInputSchema(TypedDict, total=False):
    """Fields a provider needs from a candidate to produce an observation."""

    candidate_id: str
    candidate_url: str
    candidate_title: str
    query: str
    platform: str
    region: str


class SocialHeatProviderOutputSchema(TypedDict, total=False):
    """Fields a provider guarantees in each output observation."""

    platform: str
    result_type: str
    engagement_signals: dict[str, int | float]
    url: str
    snippet: str
    timestamp: str
    evidence_texts: list[str]
    top_results: list[dict[str, str]]


class SocialHeatProviderContract(TypedDict, total=False):
    """Describes a social heat provider's interface (HEAT-001).

    Every provider must declare:
    - provider_id: unique identifier
    - platform: e.g. bilibili / weibo / reddit
    - access_method: how the provider reaches the platform
    - input_schema: what candidate fields the provider consumes
    - output_schema: what observation fields the provider emits
    """

    provider_id: str
    platform: str
    access_method: AccessMethod
    input_schema: SocialHeatProviderInputSchema
    output_schema: SocialHeatProviderOutputSchema


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCESS_METHODS: set[str] = {
    "public_search",
    "api",
    "browser_sidecar",
    "manual_import",
}

ACCESS_MODES = {
    "public_search",
    "browser_sidecar",
    "manual_import",
    "api_or_search_service",
}

STATUSES = {
    "ok",
    "blocked",
    "login_required",
    "manual_required",
    "error",
}

HEAT_VALIDITY_HINTS = {
    "game_discussion",
    "general_social_heat",
    "unclear",
}

ACCESS_STATUS = Literal[
    "public_accessible",
    "login_required",
    "browser_only",
    "api_key_required",
    "blocked",
]

RECOMMENDED_METHOD = Literal[
    "public_search",
    "api",
    "browser_sidecar",
    "manual_or_browser_required",
]

# Providers that require login — must never be silently skipped.
PROVIDERS_REQUIRING_LOGIN: set[str] = {
    "weibo",
    "xiaoheihe",
    "tieba",
    "reddit",
    "x",
    "youtube",
}

GAME_CONTEXT_TERMS = (
    "game",
    "games",
    "gaming",
    "playstation",
    "ps5",
    "ps4",
    "xbox",
    "nintendo",
    "switch",
    "steam",
    "pc",
    "trailer",
    "release",
    "demo",
    "玩家",
    "游戏",
    "主机",
    "任天堂",
    "索尼",
    "微软",
    "发售",
    "预告",
    "新作",
    "单机",
    "电玩",
)

DISCUSSION_CONTEXT_TERMS = (
    "comment",
    "comments",
    "reply",
    "replies",
    "repost",
    "reposts",
    "share",
    "shares",
    "discussion",
    "discuss",
    "debate",
    "thread",
    "trending",
    "评论",
    "弹幕",
    "转发",
    "热议",
    "讨论",
    "争议",
    "帖子",
    "播放",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_string(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_access_mode(raw: Any) -> str:
    value = _clean_string(raw).lower()
    if value in ACCESS_MODES:
        return value
    if "public" in value or "search_page" in value:
        return "public_search"
    if "manual" in value:
        return "manual_import"
    if "browser" in value or "sidecar" in value:
        return "browser_sidecar"
    if "api" in value or "service" in value:
        return "api_or_search_service"
    return "public_search"


def _normalize_status(raw: Any, *, status_code: Any = None, access_mode: str = "") -> str:
    value = _clean_string(raw).lower()
    if value == "skipped_manual":
        return "manual_required"
    if value in {"missing_url", "manual_required"}:
        return "manual_required" if access_mode == "manual_import" else "error"
    if value in {"skipped_limit", "skipped"}:
        return "manual_required" if access_mode == "manual_import" else "error"
    if value in STATUSES:
        return value
    try:
        code = int(status_code)
    except (TypeError, ValueError):
        code = 0
    if code in {401, 403}:
        return "login_required" if code == 401 else "blocked"
    if code == 429:
        return "blocked"
    return "error"


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _as_list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_clean_string(item) for item in value if _clean_string(item)]


def _combined_evidence_text(observation: dict[str, Any]) -> str:
    parts = [*observation.get("evidence_texts", [])]
    for result in observation.get("top_results", []):
        if isinstance(result, dict):
            parts.extend([result.get("title", ""), result.get("snippet", "")])
    text = " ".join(_clean_string(part) for part in parts if _clean_string(part))
    for self_reference in (
        _clean_string(observation.get("candidate_title")),
        _clean_string(observation.get("query")),
    ):
        if self_reference:
            text = text.replace(self_reference, " ")
    return " ".join(text.split()).lower()


def _has_positive_engagement(observation: dict[str, Any]) -> bool:
    signals = observation.get("engagement_signals", {})
    if not isinstance(signals, dict):
        return False
    for value in signals.values():
        if isinstance(value, (int, float)) and value > 0:
            return True
    return False


def infer_heat_validity_hint(observation: dict[str, Any]) -> str:
    """Return game_discussion, general_social_heat, or unclear."""

    explicit = _clean_string(observation.get("heat_validity_hint")).lower()
    if explicit in HEAT_VALIDITY_HINTS:
        return explicit

    text = _combined_evidence_text(observation)
    has_game_context = any(term in text for term in GAME_CONTEXT_TERMS)
    has_discussion_context = any(term in text for term in DISCUSSION_CONTEXT_TERMS)
    has_engagement = _has_positive_engagement(observation)

    if has_game_context and (has_discussion_context or has_engagement):
        return "game_discussion"
    if has_discussion_context or has_engagement:
        return "general_social_heat"
    return "unclear"


def normalize_social_heat_observation(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a complete normalized social heat observation."""

    access_mode = _normalize_access_mode(raw.get("access_mode", raw.get("access", "")))
    status = _normalize_status(raw.get("status", ""), status_code=raw.get("status_code"), access_mode=access_mode)
    observation = {
        "candidate_id": _clean_string(raw.get("candidate_id")),
        "candidate_url": _clean_string(raw.get("candidate_url")),
        "candidate_title": _clean_string(raw.get("candidate_title")),
        "platform": _clean_string(raw.get("platform")) or "unknown",
        "access_mode": access_mode,
        "query": _clean_string(raw.get("query")),
        "observed_at": _clean_string(raw.get("observed_at")) or _now_iso(),
        "status": status,
        "result_count": int(raw.get("result_count") or 0),
        "engagement_signals": _as_dict(raw.get("engagement_signals")),
        "top_results": _as_list_of_dicts(raw.get("top_results")),
        "evidence_texts": _as_list_of_strings(raw.get("evidence_texts")),
        "source_observation_status": _clean_string(raw.get("status")),
        "source_status_code": raw.get("status_code"),
        "source_url": _clean_string(raw.get("url")),
        "error": _clean_string(raw.get("error")),
    }
    explicit_hint = _clean_string(raw.get("heat_validity_hint")).lower()
    if explicit_hint in HEAT_VALIDITY_HINTS:
        observation["heat_validity_hint"] = explicit_hint
    if "discussion_hint_count" in raw:
        observation["engagement_signals"].setdefault(
            "discussion_hint_count",
            int(raw.get("discussion_hint_count") or 0),
        )
    observation["heat_validity_hint"] = infer_heat_validity_hint(observation)
    return observation


def build_social_heat_summary(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Return counts by platform, access mode, status, and heat validity hint."""

    normalized = [normalize_social_heat_observation(item) for item in observations if isinstance(item, dict)]
    platform_counts = Counter(item["platform"] for item in normalized)
    access_mode_counts = Counter(item["access_mode"] for item in normalized)
    status_counts = Counter(item["status"] for item in normalized)
    heat_validity_counts = Counter(item["heat_validity_hint"] for item in normalized)
    return {
        "total_observations": len(normalized),
        "platform_counts": dict(platform_counts),
        "access_mode_counts": dict(access_mode_counts),
        "status_counts": dict(status_counts),
        "heat_validity_counts": dict(heat_validity_counts),
        "public_search_ok": sum(
            1 for item in normalized if item["access_mode"] == "public_search" and item["status"] == "ok"
        ),
        "manual_required": status_counts.get("manual_required", 0),
        "blocked_or_login_required": status_counts.get("blocked", 0) + status_counts.get("login_required", 0),
        "game_discussion": heat_validity_counts.get("game_discussion", 0),
    }


def default_social_platform_profiles() -> list[dict[str, Any]]:
    """Return the no-login-first access profile for social heat providers."""

    return [
        {
            "platform": "bilibili",
            "region": "zh_cn",
            "default_access_mode": "public_search",
            "automatic_first_batch": True,
            "public_http_probe": "ok",
            "notes": "Basic public search page returned HTML in low-frequency probe.",
        },
        {
            "platform": "steam_discussions",
            "region": "global",
            "default_access_mode": "public_search",
            "automatic_first_batch": True,
            "public_http_probe": "ok",
            "notes": "Steam community search returned an HTML results page in low-frequency probe.",
        },
        {
            "platform": "youtube",
            "region": "global",
            "default_access_mode": "browser_sidecar",
            "automatic_first_batch": False,
            "public_http_probe": "js_shell",
            "notes": "Ordinary HTTP may return a script-heavy shell; use browser sidecar or search service later.",
        },
        {
            "platform": "x",
            "region": "global",
            "default_access_mode": "browser_sidecar",
            "automatic_first_batch": False,
            "public_http_probe": "js_shell",
            "notes": "Search UI is script-heavy and may require browser observation.",
        },
        {
            "platform": "weibo",
            "region": "zh_cn",
            "default_access_mode": "browser_sidecar",
            "automatic_first_batch": False,
            "public_http_probe": "visitor_system",
            "notes": "Basic public probe returned a visitor system page.",
        },
        {
            "platform": "tieba",
            "region": "zh_cn",
            "default_access_mode": "browser_sidecar",
            "automatic_first_batch": False,
            "public_http_probe": "blocked",
            "notes": "Basic public probe returned HTTP 403.",
        },
        {
            "platform": "reddit",
            "region": "en_global",
            "default_access_mode": "api_or_search_service",
            "automatic_first_batch": False,
            "public_http_probe": "blocked",
            "notes": "Basic public probe returned HTTP 403; prefer API/search service later.",
        },
        {
            "platform": "xiaoheihe",
            "region": "zh_cn",
            "default_access_mode": "manual_import",
            "automatic_first_batch": False,
            "public_http_probe": "no_stable_public_search",
            "notes": "No stable public web search endpoint observed; start with manual import.",
        },
    ]


def public_search_first_batch_platforms() -> list[str]:
    """Return platforms that should be attempted first without login."""

    return [
        item["platform"]
        for item in default_social_platform_profiles()
        if item["default_access_mode"] == "public_search" and item["automatic_first_batch"]
    ]


def observations_from_discussion_provider_report(provider_report: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert current DiscussionProbeProvider output into social heat observations."""

    observations = provider_report.get("observations", []) if isinstance(provider_report, dict) else []
    if not isinstance(observations, list):
        return []
    return [
        normalize_social_heat_observation(item)
        for item in observations
        if isinstance(item, dict)
    ]


# ---------------------------------------------------------------------------
# HEAT-001 — Provider Contract & Validation
# ---------------------------------------------------------------------------

REQUIRED_HEAT_OBSERVATION_FIELDS = {
    "platform",
    "result_type",
    "engagement_signals",
    "url",
    "snippet",
    "timestamp",
}


def validate_heat_observation(obs: dict[str, Any]) -> list[str]:
    """Validate that an observation contains all required fields (HEAT-001).

    Returns a list of missing field names. An empty list means the observation
    is valid.
    """
    if not isinstance(obs, dict):
        return sorted(REQUIRED_HEAT_OBSERVATION_FIELDS)

    missing: list[str] = []
    for field in sorted(REQUIRED_HEAT_OBSERVATION_FIELDS):
        if field not in obs:
            missing.append(field)
            continue
        value = obs[field]
        if field == "engagement_signals":
            if not isinstance(value, dict):
                missing.append(field)
        elif field == "url":
            if not _clean_string(value):
                missing.append(field)
        elif field == "snippet":
            if not _clean_string(value):
                missing.append(field)
        elif field == "platform":
            if not _clean_string(value):
                missing.append(field)
        elif field == "timestamp":
            if not _clean_string(value):
                missing.append(field)
        elif field == "result_type":
            if not _clean_string(value):
                missing.append(field)
    return missing


def _access_method_from_contract(method: str) -> str:
    """Map a contract access_method to the canonical ACCESS_MODES string."""
    mode = _clean_string(method).lower()
    if mode in ACCESS_MODES:
        return mode
    if mode == "api":
        return "api_or_search_service"
    if mode in {"public_search", "manual_import", "browser_sidecar"}:
        return mode
    return "public_search"


def _map_output_field(
    raw_obs: dict[str, Any],
    contract: dict[str, Any],
    field: str,
) -> Any:
    """Resolve a unified field from raw provider output using the contract's
    output_schema mapping.

    The output_schema can contain either a field name directly (indicating the
    provider output uses the same name) or a nested mapping with a ``source``
    key that names the field in the raw observation.
    """
    output_schema = _as_dict(contract.get("output_schema"))

    # If the contract declares a mapping for this field via a "source" key,
    # follow it.
    field_mapping = output_schema.get(field)
    if isinstance(field_mapping, dict) and "source" in field_mapping:
        source_key = str(field_mapping["source"])
        value = raw_obs.get(source_key)
        # Allow a ``default`` override.
        if value is None and "default" in field_mapping:
            value = field_mapping["default"]
        return value

    # If the output_schema lists the field name as a key (even if the value
    # is not a dict), the provider is expected to emit that field directly.
    if field in output_schema:
        return raw_obs.get(field)

    # Fallback: try the field name directly.
    return raw_obs.get(field)


def normalize_heat_observation(
    raw_obs: dict[str, Any],
    provider_contract: dict[str, Any],
) -> dict[str, Any]:
    """Normalize a raw provider observation into the unified format (HEAT-001).

    Uses the provider's output_schema to map provider-specific field names to
    the canonical observation shape.
    """
    if not isinstance(raw_obs, dict):
        raw_obs = {}
    contract = dict(provider_contract) if isinstance(provider_contract, dict) else {}

    access_method = _access_method_from_contract(
        contract.get("access_method", "public_search")
    )
    platform = _clean_string(
        _map_output_field(raw_obs, contract, "platform")
        or contract.get("platform")
        or "unknown"
    )

    result_type = _clean_string(
        _map_output_field(raw_obs, contract, "result_type") or "unknown"
    )

    engagement_signals = _as_dict(
        _map_output_field(raw_obs, contract, "engagement_signals")
    )

    url = _clean_string(_map_output_field(raw_obs, contract, "url"))

    snippet = _clean_string(_map_output_field(raw_obs, contract, "snippet"))

    timestamp = _clean_string(
        _map_output_field(raw_obs, contract, "timestamp") or _now_iso()
    )

    evidence_texts = _as_list_of_strings(
        _map_output_field(raw_obs, contract, "evidence_texts")
    )

    top_results = _as_list_of_dicts(
        _map_output_field(raw_obs, contract, "top_results")
    )

    observation: dict[str, Any] = {
        "provider_id": _clean_string(contract.get("provider_id") or raw_obs.get("provider_id")),
        "platform": platform,
        "result_type": result_type,
        "engagement_signals": engagement_signals,
        "url": url,
        "snippet": snippet,
        "timestamp": timestamp,
        "access_method": access_method,
        "evidence_texts": evidence_texts,
        "top_results": top_results,
        "candidate_id": _clean_string(raw_obs.get("candidate_id")),
        "candidate_url": _clean_string(raw_obs.get("candidate_url")),
        "candidate_title": _clean_string(raw_obs.get("candidate_title")),
        "query": _clean_string(raw_obs.get("query")),
    }

    # Forward-compat: carry through any extra fields the provider emits that
    # the contract declares.
    output_schema = _as_dict(contract.get("output_schema"))
    for field_name in output_schema:
        if field_name not in observation:
            observation[field_name] = _map_output_field(raw_obs, contract, field_name)

    # Attach heat validity hint using the same inference as normalize_social_heat_observation.
    observation["heat_validity_hint"] = infer_heat_validity_hint(
        {
            "candidate_title": observation.get("candidate_title"),
            "query": observation.get("query"),
            "engagement_signals": observation.get("engagement_signals"),
            "evidence_texts": observation.get("evidence_texts"),
            "top_results": observation.get("top_results"),
        }
    )

    return observation


# ---------------------------------------------------------------------------
# HEAT-004 — Login Boundary
# ---------------------------------------------------------------------------

_PROVIDER_ACCESS_PROFILES: dict[str, dict[str, Any]] = {
    "bilibili": {
        "access_status": "public_accessible",
        "recommended_method": "public_search",
        "compliance_notes": (
            "Public search page returns HTML in low-frequency probe. "
            "No login required for basic search."
        ),
    },
    "steam_discussions": {
        "access_status": "public_accessible",
        "recommended_method": "public_search",
        "compliance_notes": (
            "Steam community search returns an HTML results page. "
            "No login required."
        ),
    },
    "youtube": {
        "access_status": "browser_only",
        "recommended_method": "browser_sidecar",
        "compliance_notes": (
            "Script-heavy shell on plain HTTP. "
            "Search requires browser-side execution; login may be needed for "
            "comment access. Marked manual_or_browser_required."
        ),
    },
    "x": {
        "access_status": "login_required",
        "recommended_method": "manual_or_browser_required",
        "compliance_notes": (
            "Search UI is script-heavy. Login wall blocks unauthenticated "
            "access. Must use browser sidecar or manual import — never "
            "silently skip."
        ),
    },
    "weibo": {
        "access_status": "login_required",
        "recommended_method": "manual_or_browser_required",
        "compliance_notes": (
            "Public probe returns a visitor-system page. Full search requires "
            "login or browser session. Must not be silently skipped."
        ),
    },
    "tieba": {
        "access_status": "blocked",
        "recommended_method": "manual_or_browser_required",
        "compliance_notes": (
            "Basic public probe returned HTTP 403. Access requires browser "
            "session or manual import. Must not be silently skipped."
        ),
    },
    "reddit": {
        "access_status": "blocked",
        "recommended_method": "api",
        "compliance_notes": (
            "Public probe returned HTTP 403. Prefer API with key or "
            "search-service fallback. Must not be silently skipped."
        ),
    },
    "xiaoheihe": {
        "access_status": "login_required",
        "recommended_method": "manual_or_browser_required",
        "compliance_notes": (
            "No stable public web search endpoint. Manual import or browser "
            "sidecar required. Must not be silently skipped."
        ),
    },
}


def check_provider_access(
    provider_config: dict[str, Any],
) -> dict[str, Any]:
    """Determine access viability for a social heat provider (HEAT-004).

    Returns a dict with:
    - access_status: public_accessible / login_required / browser_only /
      api_key_required / blocked
    - recommended_method: public_search / api / browser_sidecar /
      manual_or_browser_required
    - compliance_notes: human-readable explanation
    - requires_login: bool — True when the provider must not be silently
      skipped (always true for login_required / blocked / browser_only
      unless public_accessible).

    Providers requiring login or browser sessions are marked
    ``manual_or_browser_required`` and are never silently skipped.
    """
    if not isinstance(provider_config, dict):
        return {
            "access_status": "blocked",
            "recommended_method": "manual_or_browser_required",
            "compliance_notes": "Invalid or missing provider configuration.",
            "requires_login": True,
        }

    platform = _clean_string(provider_config.get("platform"))
    if not platform:
        return {
            "access_status": "blocked",
            "recommended_method": "manual_or_browser_required",
            "compliance_notes": "Provider configuration missing 'platform' field.",
            "requires_login": True,
        }

    # Check built-in profiles first.
    profile = _PROVIDER_ACCESS_PROFILES.get(platform)
    if profile is not None:
        result = dict(profile)
        result["platform"] = platform
        result["requires_login"] = result["access_status"] in {
            "login_required",
            "blocked",
            "browser_only",
            "api_key_required",
        }
        return result

    # Fallback: infer from provider_config fields.
    public_http_probe = _clean_string(provider_config.get("public_http_probe"))
    default_access_mode = _clean_string(provider_config.get("default_access_mode"))
    notes = _clean_string(provider_config.get("notes", ""))

    if public_http_probe == "ok":
        access_status: str = "public_accessible"
        rec_method: str = "public_search"
        compliance = notes or "Public search endpoint probe succeeded."
    elif public_http_probe in {"js_shell", "visitor_system"}:
        access_status = "login_required"
        rec_method = "manual_or_browser_required"
        compliance = notes or (
            "Probe returned a login/visitor wall. "
            "Search requires browser sidecar or manual import."
        )
    elif public_http_probe in {"blocked", "403", "401"}:
        access_status = "blocked"
        if default_access_mode == "api_or_search_service":
            rec_method = "api"
        else:
            rec_method = "manual_or_browser_required"
        compliance = notes or "Public probe blocked with HTTP 401/403."
    elif platform in PROVIDERS_REQUIRING_LOGIN:
        access_status = "login_required"
        rec_method = "manual_or_browser_required"
        compliance = notes or (
            f"Platform '{platform}' is known to require login. "
            "Must not be silently skipped."
        )
    else:
        access_status = "public_accessible"
        rec_method = "public_search"
        compliance = notes or "No known access restrictions."

    return {
        "access_status": access_status,
        "recommended_method": rec_method,
        "compliance_notes": compliance,
        "platform": platform,
        "requires_login": access_status in {
            "login_required",
            "blocked",
            "browser_only",
            "api_key_required",
        },
    }


def provider_requires_manual_intervention(provider_config: dict[str, Any]) -> bool:
    """Return True when the provider cannot be used automatically (HEAT-004).

    Convenience wrapper around ``check_provider_access``.
    """
    access = check_provider_access(provider_config)
    return access.get("requires_login", True)
