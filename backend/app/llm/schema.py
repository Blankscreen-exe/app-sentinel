"""The structured decision the planner must return. Validated before anything runs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgentDecision(BaseModel):
    """One planner step. `action` is a registered tool name or the literal 'stop'."""

    model_config = ConfigDict(extra="forbid")

    objective: str = Field(description="what this step is trying to learn or establish")
    hypothesis_id: str | None = Field(default=None, description="hypothesis this addresses, if any")
    action: str = Field(description="a registered tool name, or 'stop'")
    arguments: dict = Field(default_factory=dict, description="validated arguments for the tool")
    expected_observation: str = Field(description="what the tool is expected to reveal")
    rationale: str = Field(description="why this action, given the evidence")
    uncertainty: list[str] = Field(default_factory=list, description="open unknowns")
    stop_reason: str | None = Field(default=None, description="set only when action == 'stop'")


def decision_schema(allowed_actions: list[str]) -> dict:
    """JSON schema for the decision, with `action` constrained to allowed tool names."""
    schema = AgentDecision.model_json_schema()
    schema["properties"]["action"]["enum"] = [*allowed_actions, "stop"]
    return schema
