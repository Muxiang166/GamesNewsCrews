"""Deterministic evidence verifier scaffold."""

from __future__ import annotations

import re
from typing import Any


STOPWORDS = {
    "a",
    "an",
    "and",
    "after",
    "in",
    "is",
    "of",
    "online",
    "the",
    "to",
}

# ---------------------------------------------------------------------------
# VER-003  Rumor Tiering
# ---------------------------------------------------------------------------

CAUSAL_PATTERNS_ZH = re.compile(
    r"导致|因为|由于|引起|造成|所以|因此|因而|从而|致使|归因于|缘故",
)
CAUSAL_PATTERNS_EN = re.compile(
    r"\b(therefore|because|due to|caused by|caused|led to|leads to|leading to|"
    r"as a result|resulting from|owing to|hence|thus|consequently|"
    r"attributed to|on account of)\b",
    flags=re.IGNORECASE,
)

FLAGGED_TOPIC_PATTERNS = {
    "price_increase": re.compile(
        r"涨价|价格上涨|价格上调|price increase|price hike|price rise|"
        r"定价|售价|售价上涨|涨价了|更贵",
        flags=re.IGNORECASE,
    ),
    "layoff": re.compile(
        r"裁员|解散|关闭工作室|关闭团队|layoff|lay off|laid off|"
        r"studio closure|team disbanded|restructuring|downsiz",
        flags=re.IGNORECASE,
    ),
    "dei": re.compile(
        r"(?<![a-zA-Z])DEI(?![a-zA-Z])|包容性|多元化|多样性|包容|diversity.*equity.*inclusion|"
        r"多元化.*公平.*包容|政治正确",
        flags=re.IGNORECASE,
    ),
    "revenue_decline": re.compile(
        r"营收下降|收入下降|亏损|利润下滑|revenue decline|revenue drop|"
        r"profit decline|loss|financial trouble|财报不佳|业绩下滑",
        flags=re.IGNORECASE,
    ),
}

RUMOR_TIER_LABELS: dict[str, str] = {
    "credible_rumor": "[流言][可信爆料]",
    "weak_rumor": "[流言][待验证]",
    "unverified_rumor": "[流言][未验证]",
}


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower()):
        if raw in STOPWORDS or len(raw) <= 1:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", raw):
            if len(raw) == 2:
                tokens.add(raw)
            else:
                tokens.update(raw[index : index + 2] for index in range(len(raw) - 1))
        else:
            tokens.add(raw)
    return tokens


def _evidence_for_claim(
    claim: dict[str, Any],
    evidence_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    wanted_chunk_ids = {
        str(chunk_id)
        for chunk_id in claim.get("evidence_chunk_ids", [])
        if str(chunk_id).strip()
    }
    wanted_urls = {
        str(url)
        for url in claim.get("source_urls", [])
        if str(url).strip()
    }
    evidence: list[dict[str, Any]] = []
    for chunk in evidence_chunks:
        chunk_id = str(chunk.get("chunk_id", ""))
        url = str(chunk.get("url", ""))
        if (wanted_chunk_ids and chunk_id in wanted_chunk_ids) or (
            wanted_urls and url in wanted_urls
        ):
            evidence.append(dict(chunk))
    return evidence


def _support_score(claim_text: str, evidence: list[dict[str, Any]]) -> float:
    claim_tokens = _tokens(claim_text)
    if not claim_tokens or not evidence:
        return 0.0
    evidence_text = " ".join(str(item.get("quote", "")) for item in evidence).lower()
    hits = sum(1 for token in claim_tokens if token in evidence_text)
    return hits / max(len(claim_tokens), 1)


def _status_for_claim(
    claim: dict[str, Any],
    evidence: list[dict[str, Any]],
    support_score: float,
) -> tuple[str, float, list[str]]:
    if not evidence:
        return "reject", 0.0, ["missing_evidence"]

    claim_type = str(claim.get("claim_type", ""))
    if claim_type == "supplemental_context":
        return "reject", 0.1, ["supplemental_context_not_publishable"]
    if claim_type == "search_lead":
        return "reject", 0.1, ["search_lead_requires_confirmation"]
    if claim_type == "rumor":
        confidence = 0.35 + min(support_score, 1.0) * 0.25
        return "rumor", round(confidence, 2), ["rumor_claim_with_evidence"]

    if support_score >= 0.45:
        confidence = 0.45 + min(support_score, 1.0) * 0.35
        return "likely", round(confidence, 2), ["supporting_evidence_overlap"]

    if claim_type in {"news", "hardware_platform", "platform_price"} and support_score >= 0.25:
        confidence = 0.38 + min(support_score, 1.0) * 0.28
        return "likely", round(confidence, 2), ["partial_supporting_evidence_overlap"]

    return "reject", 0.1, ["weak_or_unmatched_evidence"]


def verify_claims_against_evidence(
    claims: list[dict[str, Any]],
    evidence_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    verifications: list[dict[str, Any]] = []
    for claim in claims:
        evidence = _evidence_for_claim(claim, evidence_chunks)
        score = _support_score(str(claim.get("text", "")), evidence)
        status, confidence, reasons = _status_for_claim(claim, evidence, score)
        verified = dict(claim)
        verified["check_status"] = status
        verified["confidence"] = confidence
        verified["verification_reasons"] = reasons
        verified["verification_method"] = "deterministic_evidence_overlap_v0"
        verified["support_score"] = round(score, 3)
        verified["evidence"] = evidence
        verifications.append(verified)
    return verifications


# ---------------------------------------------------------------------------
# VER-003  Rumor Tiering
# ---------------------------------------------------------------------------


def _count_unique_sources(evidence: list[dict[str, Any]]) -> int:
    """Count unique source domains/IDs across evidence chunks."""
    sources: set[str] = set()
    for chunk in evidence:
        source = str(chunk.get("source_id") or chunk.get("url") or "").strip()
        if source:
            sources.add(source)
    return max(len(sources), 1)


def _authority_cited(verification_reasons: list[str]) -> bool:
    """Check whether an authority (official, verified account, etc.) is cited."""
    authority_markers = {
        "authority_cited",
        "official_source",
        "verified_account",
        "press_release",
        "developer_statement",
        "publisher_confirmed",
    }
    return any(
        str(reason).lower() in authority_markers
        for reason in verification_reasons
    )


def _known_accurate_leaker(source_credibility: dict[str, Any], claim: dict[str, Any]) -> bool:
    """Determine whether the claim's source has a track record of accuracy."""
    source_urls = claim.get("source_urls", [])
    if not source_urls:
        return False
    for url in source_urls:
        source_id = str(url).strip()
        cred = source_credibility.get(source_id) if isinstance(source_credibility, dict) else None
        if isinstance(cred, dict):
            track = str(cred.get("track_record", "")).lower()
            if track in {"proven_accurate", "reliable", "verified"}:
                return True
            accuracy = float(cred.get("historical_accuracy", 0))
            if accuracy >= 0.8:
                return True
    return False


def tier_rumor(
    claim: dict[str, Any],
    verification_result: dict[str, Any],
    source_credibility: dict[str, Any],
) -> dict[str, Any]:
    """Assign a rumor tier and external label based on evidence and source credibility.

    Args:
        claim: The claim dict (must include ``claim_type``, ``source_urls``,
            ``text``).
        verification_result: Output from ``verify_claims_against_evidence``
            (``check_status``, ``confidence``, ``support_score``,
            ``verification_reasons``, ``evidence``).
        source_credibility: Mapping of source URL/id to credibility metadata
            (``track_record``, ``historical_accuracy``, ``is_leaker``).

    Returns:
        A dict with keys ``tier``, ``external_label``, ``confidence``,
        and ``reasons``.
    """
    evidence = verification_result.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
    confidence = float(verification_result.get("confidence", 0))
    support_score = float(verification_result.get("support_score", 0))
    reasons: list[str] = list(verification_result.get("verification_reasons", []))

    num_sources = _count_unique_sources(evidence)
    has_authority = _authority_cited(reasons)
    is_known_leaker = _known_accurate_leaker(source_credibility, claim)

    # ---- tier determination ----
    # credible_rumor: known accurate leaker + multiple corroborating sources,
    #   or cited by an authority with decent support.
    if (is_known_leaker and num_sources >= 2) or (has_authority and support_score >= 0.3):
        tier = "credible_rumor"
        tier_reasons = ["known_accurate_leaker_multiple_sources" if is_known_leaker else "authority_cited"]
        adjusted_confidence = min(confidence + 0.15, 0.95)
    elif num_sources >= 2 or support_score >= 0.2:
        # weak_rumor: single source with some evidence, unknown leaker, vague.
        tier = "weak_rumor"
        tier_reasons = ["limited_corroboration"]
        adjusted_confidence = min(confidence + 0.05, 0.65)
    else:
        # unverified_rumor: no track record, contradictory or absent evidence.
        tier = "unverified_rumor"
        tier_reasons = ["no_track_record_or_contradictory"]
        adjusted_confidence = min(confidence, 0.35)

    return {
        "tier": tier,
        "external_label": RUMOR_TIER_LABELS[tier],
        "confidence": round(adjusted_confidence, 2),
        "reasons": tier_reasons,
    }


# ---------------------------------------------------------------------------
# VER-004  Causal Claim Guard
# ---------------------------------------------------------------------------


def detect_causal_claim(claim_text: str) -> dict[str, Any]:
    """Detect causal language and flag sensitive topics in a claim.

    Args:
        claim_text: The natural-language claim string.

    Returns:
        A dict with ``is_causal``, ``causal_markers_found``,
        ``flagged_topics``, and ``requires_review``.
    """
    text = str(claim_text)
    zh_matches = CAUSAL_PATTERNS_ZH.findall(text)
    en_matches = CAUSAL_PATTERNS_EN.findall(text)
    all_markers = zh_matches + en_matches
    is_causal = len(all_markers) > 0

    flagged_topics: list[str] = []
    for topic, pattern in FLAGGED_TOPIC_PATTERNS.items():
        if pattern.search(text):
            flagged_topics.append(topic)

    requires_review = is_causal and len(flagged_topics) > 0

    return {
        "is_causal": is_causal,
        "causal_markers_found": sorted(set(all_markers)),
        "flagged_topics": flagged_topics,
        "requires_review": requires_review,
    }


def split_fact_from_inference(claim_text: str) -> dict[str, Any]:
    """Separate an observable factual event from its causal inference portion.

    The function uses the first causal marker as a split point: everything
    before it is treated as the *factual_part* (what happened) and everything
    from the marker onward is the *inference_part* (why it happened).

    Args:
        claim_text: The natural-language claim string.

    Returns:
        A dict with ``factual_part``, ``inference_part``,
        ``fact_confidence``, ``inference_confidence``, ``split_marker``,
        and ``is_separable``.
    """
    text = str(claim_text).strip()
    if not text:
        return {
            "factual_part": "",
            "inference_part": "",
            "fact_confidence": 0.0,
            "inference_confidence": 0.0,
            "split_marker": "",
            "is_separable": False,
        }

    # Find the earliest causal marker position
    zh_matches = [(m.group(), m.start()) for m in CAUSAL_PATTERNS_ZH.finditer(text)]
    en_matches = [(m.group(), m.start()) for m in CAUSAL_PATTERNS_EN.finditer(text)]
    all_matches = zh_matches + en_matches
    all_matches.sort(key=lambda item: item[1])

    if not all_matches:
        # No causal marker — the whole text is factual
        return {
            "factual_part": text,
            "inference_part": "",
            "fact_confidence": 0.9,
            "inference_confidence": 0.0,
            "split_marker": "",
            "is_separable": False,
        }

    marker, pos = all_matches[0]
    factual_part = text[:pos].strip()
    inference_part = text[pos:].strip()

    # Confidence heuristics
    # Longer factual part with clear event language → higher confidence
    fact_len = len(factual_part)
    inference_len = len(inference_part)

    if fact_len >= 10 and inference_len >= 5:
        fact_confidence = 0.75
        inference_confidence = 0.7
    elif fact_len >= 10:
        fact_confidence = 0.8
        inference_confidence = 0.5
    elif inference_len >= 5:
        fact_confidence = 0.5
        inference_confidence = 0.7
    else:
        fact_confidence = 0.4
        inference_confidence = 0.4

    # Boost factual confidence when it contains observable-event language
    observable_patterns = re.compile(
        r"宣布|公布|发布|上线|发售|更新|关闭|裁员|"
        r"announced|released|launched|updated|closed|"
        r"reported|confirmed|stated",
        flags=re.IGNORECASE,
    )
    if observable_patterns.search(factual_part):
        fact_confidence = min(fact_confidence + 0.15, 0.95)

    return {
        "factual_part": factual_part,
        "inference_part": inference_part,
        "fact_confidence": round(fact_confidence, 2),
        "inference_confidence": round(inference_confidence, 2),
        "split_marker": marker,
        "is_separable": True,
    }
