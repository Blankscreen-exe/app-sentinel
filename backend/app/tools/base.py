"""Tool interface, normalized result, and the registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolResult:
    """Normalized tool output — never raw terminal text.

    `outcome_signal` is the raw, factual signal the tool observed (e.g. HTTP status,
    row count). The *verifier* interprets it into a verdict; the tool does not decide
    whether something is a vulnerability.
    """

    ok: bool
    tool: str
    signal: dict[str, Any] = field(default_factory=dict)
    error_category: str | None = None  # network_error | tool_failure | None
    evidence: dict[str, Any] = field(default_factory=dict)


class SecurityTool(Protocol):
    name: str
    description: str
    is_active_network: bool
    risk_level: str

    def run(self, context: dict[str, Any], arguments: dict[str, Any]) -> ToolResult: ...


_REGISTRY: dict[str, SecurityTool] = {}


def register(tool: SecurityTool) -> SecurityTool:
    if tool.name in _REGISTRY:
        raise ValueError(f"tool already registered: {tool.name}")
    _REGISTRY[tool.name] = tool
    return tool


def get_tool(name: str) -> SecurityTool | None:
    return _REGISTRY.get(name)


def registered_names() -> list[str]:
    return sorted(_REGISTRY)
