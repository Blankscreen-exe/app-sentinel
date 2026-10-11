"""Registered security tools.

The agent may only invoke tools registered here, by name, with validated arguments. A
tool never receives arbitrary execution capability. Each active tool enforces scope and
data-minimization itself, independently of the planner.
"""
