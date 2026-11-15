"""
NLE-Bench Canonical Tools (25 tools)

Defines tool schemas (OpenAI function-calling format) and reference implementations
for the Canonical Track. Uses EditProject from nlebench.models (no external deps).
"""

from nlebench.tools.schema import (
    CANONICAL_TOOLS,
    LEGACY_TOOL_NAME_MAP,
    TOOL_SCHEMAS,
    CORE_TOOLS,
    SUPPLEMENTARY_TOOLS,
)
from nlebench.tools.executor import execute_tool, TOOL_HANDLERS
from nlebench.protocols import ToolSchema


def get_tool_schemas() -> list[ToolSchema]:
    """Get canonical tools as ToolSchema objects.

    Converts the OpenAI function-calling format to ToolSchema dataclass.

    Returns:
        List of 25 canonical tool schemas
    """
    schemas = []
    for tool_dict in TOOL_SCHEMAS:
        func = tool_dict.get("function", {})
        schemas.append(ToolSchema(
            name=func.get("name", ""),
            description=func.get("description", ""),
            parameters=func.get("parameters", {}),
        ))
    return schemas


__all__ = [
    "CANONICAL_TOOLS",
    "LEGACY_TOOL_NAME_MAP",
    "TOOL_SCHEMAS",
    "CORE_TOOLS",
    "SUPPLEMENTARY_TOOLS",
    "execute_tool",
    "get_tool_schemas",
    "TOOL_HANDLERS",
]
