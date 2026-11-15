"""
NLEBench Multi-turn Support

Handles template-based message resolution for L4 multi-turn scenarios.

The user_messages in a scenario YAML can reference variables extracted
from previous agent responses, e.g.:

    user_messages:
      - text: "V1에 자막 추가해줘 '안녕하세요' 0~3초"
        extract:
          created_id: "regex: (caption_\\d+)"

      - text: "{created_id}를 강조체로 바꿔줘"
        fallback: "방금 만든 자막을 강조체로 바꿔줘"
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def extract_created_id(response: str, pattern: str = r"(caption_\d+|clip_\d+|track_\d+)") -> Optional[str]:
    """
    Extract a created entity ID from agent response text.

    Args:
        response: Agent response text
        pattern: Regex pattern to extract the ID.
                 If prefixed with "regex: ", that prefix is stripped.

    Returns:
        Extracted ID string, or None if not found
    """
    # Strip "regex: " prefix if present (from YAML format)
    if pattern.startswith("regex: "):
        pattern = pattern[len("regex: "):]

    match = re.search(pattern, response)
    if match:
        extracted = match.group(1) if match.lastindex else match.group(0)
        logger.debug(f"Extracted ID from response: {extracted}")
        return extracted

    logger.debug(f"No ID matched pattern '{pattern}' in response")
    return None


def resolve_template(message: str | dict, context: dict[str, str]) -> str:
    """
    Resolve a user message template using context variables.

    Supports two message formats:
    1. Simple string: "V1에 자막 추가해줘"
    2. Dict with template: {"text": "{created_id}를 강조체로", "fallback": "방금 만든 거 강조체로"}

    Args:
        message: Either a plain string or a dict with 'text' and optional 'fallback'
        context: Variable mapping, e.g. {"created_id": "caption_42"}

    Returns:
        Resolved message string
    """
    if isinstance(message, str):
        return _substitute(message, context)

    if isinstance(message, dict):
        text = message.get("text", "")
        fallback = message.get("fallback")

        resolved = _substitute(text, context)

        # If any placeholders remain unresolved, use fallback
        if re.search(r"\{[a-zA-Z_]\w*\}", resolved) and fallback:
            logger.debug(f"Unresolved placeholders in '{resolved}', using fallback")
            return fallback

        return resolved

    return str(message)


def extract_variables(message: str | dict, response: str) -> dict[str, str]:
    """
    Extract variables from agent response based on message extract config.

    Args:
        message: The message dict that may contain an 'extract' field
        response: Agent response text

    Returns:
        Dict of extracted variable name -> value
    """
    if not isinstance(message, dict):
        return {}

    extracts = message.get("extract", {})
    result = {}

    for var_name, pattern in extracts.items():
        value = extract_created_id(response, str(pattern))
        if value:
            result[var_name] = value

    return result


def _substitute(text: str, context: dict[str, str]) -> str:
    """Substitute {var_name} placeholders with context values."""
    for key, value in context.items():
        text = text.replace(f"{{{key}}}", value)
    return text
