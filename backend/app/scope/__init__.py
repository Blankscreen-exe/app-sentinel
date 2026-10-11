"""Deterministic scope + permission enforcement (outside the LLM).

The scope gate and network guard decide what an assessment is allowed to do. The LLM
never participates in these decisions, so no model output or prompt injection can widen
scope.
"""
