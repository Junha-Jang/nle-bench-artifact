"""
NLEBench Calibration Metrics

RAR (Refusal Accuracy Rate) - For infeasible scenarios.
CQS helpers are retained for legacy corpora that populate missing-parameter
labels. The released v3.1 paper metric for ambiguous scenarios is the stricter
clarification-without-state-change proxy described in the paper, not a
correct-missing-parameter score.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nlebench.models import ExecutionResult, Scenario

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword lists
# ---------------------------------------------------------------------------

REFUSAL_KEYWORDS_KO = [
    "불가능",
    "할 수 없",
    "지원하지 않",
    "지원되지 않",
    "처리할 수 없",
    "기능이 없",
    "제공하지 않",
    "수행할 수 없",
    "어렵습니다",
    "불가합니다",
    "분석할 수 없",
    "판단할 수 없",
    "인식할 수 없",
    "감지할 수 없",
]

REFUSAL_KEYWORDS_EN = [
    "cannot",
    "unable to",
    "not supported",
    "not possible",
    "don't have the ability",
    "can't",
    "impossible",
    "beyond my capabilities",
    "not capable",
    "do not support",
]

CLARIFICATION_KEYWORDS_KO = [
    "어떤",
    "어디",
    "몇 초",
    "무슨",
    "구체적으로",
    "확인",
    "지정",
    "알려주",
    "정확히",
    "어느",
    "말씀해",
]

CLARIFICATION_KEYWORDS_EN = [
    "which",
    "what",
    "where",
    "when",
    "how",
    "could you specify",
    "please clarify",
    "can you tell me",
    "do you mean",
]

# Fuzzy matching: clarification key -> question patterns (Korean + English)
_CLARIFICATION_KEY_MAP: dict[str, list[str]] = {
    "text_content": ["텍스트", "내용", "어떤 글", "무슨 자막", "무슨 내용",
                      "text", "content", "what text", "what word"],
    "text": ["텍스트", "내용", "text", "content", "what text"],
    "content": ["내용", "content", "text", "what text"],
    "start_time": ["시작", "몇 초부터", "언제부터", "시작 시간",
                    "start", "begin", "from when"],
    "end_time": ["끝", "몇 초까지", "언제까지", "종료 시간",
                  "end", "until", "to when"],
    "time_range": ["시간", "구간", "몇 초", "언제",
                    "time", "duration", "how long", "when"],
    "duration": ["시간", "구간", "duration", "how long", "length"],
    "caption_style": ["스타일", "어떤 자막", "종류", "타입",
                       "style", "type", "font", "format"],
    "style": ["스타일", "style", "font", "format"],
    "track": ["트랙", "어디에", "어느 트랙",
              "track", "where", "which track"],
    "position": ["위치", "어디", "position", "where", "placement", "location"],
    "target": ["어떤", "무엇을", "뭘", "어느 것",
               "which", "what", "target"],
    "amount": ["얼마나", "몇", "어느 정도",
               "how much", "how many", "amount", "level"],
    "direction": ["어디로", "어느 쪽", "direction", "where to"],
    "criteria": ["기준", "조건", "어떤 기준", "criteria", "condition"],
    "volume": ["볼륨", "소리", "volume", "audio level", "loudness"],
    "speed": ["속도", "speed", "rate", "pace"],
    "effect_type": ["효과", "이펙트", "effect", "filter"],
}


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def check_refusal(response_text: str) -> bool:
    """Check if agent response contains a refusal."""
    text_lower = response_text.lower()
    all_keywords = REFUSAL_KEYWORDS_KO + REFUSAL_KEYWORDS_EN
    return any(kw in text_lower for kw in all_keywords)


def check_state_unchanged(initial_json: str, final_json: str) -> bool:
    """Check if state was not modified (for infeasible scenarios)."""
    return initial_json == final_json


def check_clarification(response_text: str) -> bool:
    """Check if agent asked for clarification."""
    all_keywords = CLARIFICATION_KEYWORDS_KO + CLARIFICATION_KEYWORDS_EN
    # Question mark is a strong signal
    if "?" in response_text:
        return True
    return any(kw in response_text for kw in all_keywords)


# ---------------------------------------------------------------------------
# RAR
# ---------------------------------------------------------------------------


def calculate_rar(
    results: list[ExecutionResult],
    scenarios: dict[str, Scenario],
) -> float:
    """
    Refusal Accuracy Rate.

    RAR = appropriate_refusals / total_infeasible

    Appropriate refusal: agent refused AND state was not changed.
    Returns 1.0 if no infeasible scenarios exist (vacuously true).
    """
    infeasible = [
        r
        for r in results
        if r.scenario_id in scenarios
        and scenarios[r.scenario_id].feasibility == "infeasible"
    ]

    if not infeasible:
        return 1.0

    appropriate = sum(
        1
        for r in infeasible
        if r.validation.refusal_appropriate is True
        and r.validation.state_changed is False
    )

    return appropriate / len(infeasible)


# ---------------------------------------------------------------------------
# CQS helpers
# ---------------------------------------------------------------------------


def calculate_clarification_coverage(
    response_text: str,
    required_clarifications: list[str],
) -> float:
    """Fraction of required clarification items addressed in the response."""
    if not required_clarifications:
        return 1.0

    covered = sum(
        1
        for item in required_clarifications
        if _fuzzy_match(item, response_text)
    )

    return covered / len(required_clarifications)


def _fuzzy_match(clarification_key: str, response: str) -> bool:
    """Match a clarification key against agent response using keyword mapping."""
    keywords = _CLARIFICATION_KEY_MAP.get(
        clarification_key, [clarification_key]
    )
    response_lower = response.lower()
    return any(kw.lower() in response_lower for kw in keywords)


# ---------------------------------------------------------------------------
# CQS
# ---------------------------------------------------------------------------


def count_questions(response_text: str) -> int:
    """Count the number of questions in the response."""
    return response_text.count("?")


def _extract_asked_params(response_text: str, missing_parameters: list[str]) -> list[str]:
    """Extract which missing parameters the agent asked about."""
    asked = []
    for param in missing_parameters:
        if _fuzzy_match(param, response_text):
            asked.append(param)
    return asked


def calculate_cqs_single(
    response_text: str,
    asked_clarification: bool,
    state_changed: bool,
    missing_parameters: list[str],
) -> float:
    """
    CQS for a single ambiguous scenario (F1-based).

    CQS = detection × F1 × no_change

    Components:
    - detection: 1 if clarification detected, 0 otherwise
    - precision = |asked ∩ missing| / |asked|
    - recall = |asked ∩ missing| / |missing|
    - F1 = 2 × precision × recall / (precision + recall)
    - no_change: 1 if state unchanged, 0 otherwise
    """
    # Gate: must ask for clarification
    if not asked_clarification:
        return 0.0

    # Gate: must not change state
    if state_changed:
        return 0.0

    if not missing_parameters:
        return 1.0  # No missing params to ask about

    # Extract what the agent asked about
    asked = _extract_asked_params(response_text, missing_parameters)
    asked_count = max(len(asked), count_questions(response_text))

    # Precision & Recall
    relevant_asked = len(asked)  # |asked ∩ missing|
    total_asked = max(asked_count, relevant_asked)  # |asked| (at least as many as matched)
    total_missing = len(missing_parameters)  # |missing|

    if total_asked == 0:
        return 0.0

    precision = relevant_asked / total_asked if total_asked > 0 else 0.0
    recall = relevant_asked / total_missing if total_missing > 0 else 0.0

    if precision + recall == 0:
        return 0.0

    f1 = 2 * precision * recall / (precision + recall)
    return f1


def calculate_cqs(
    results: list[ExecutionResult],
    scenarios: dict[str, Scenario],
) -> float:
    """
    Legacy Clarification Quality Score (F1-based, deterministic, LLM-free).

    CQS = detection × F1 × no_change

    This helper is meaningful only when ambiguous scenarios populate
    `missing_parameters` or `required_clarifications`. The submitted v3.1 corpus
    leaves those fields empty, so paper SR-ambiguous reports the detector/BPM
    clarification-without-state-change proxy rather than this missing-parameter
    quality score.

    Where:
    - detection = 1 if clarification detected, 0 otherwise
    - F1 = harmonic mean of precision and recall
      - precision = |asked ∩ missing| / |asked| (over-questioning penalty)
      - recall = |asked ∩ missing| / |missing| (under-questioning penalty)
    - no_change = 1 if state unchanged, 0 otherwise

    Returns 1.0 if no ambiguous scenarios exist (vacuously true).
    """
    ambiguous = [
        r
        for r in results
        if r.scenario_id in scenarios
        and scenarios[r.scenario_id].feasibility == "ambiguous"
    ]

    if not ambiguous:
        return 1.0

    total_score = 0.0

    for r in ambiguous:
        scenario = scenarios[r.scenario_id]

        missing = scenario.missing_parameters or scenario.required_clarifications or []
        asked = bool(r.validation.asked_clarification)
        changed = bool(r.validation.state_changed)

        score = calculate_cqs_single(
            r.agent_response, asked, changed, missing,
        )
        total_score += score

    return total_score / len(ambiguous)
