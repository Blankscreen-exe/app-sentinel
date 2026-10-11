"""Provider-independent LLM access for the agent planner.

The LLM only proposes structured decisions. It never authorizes actions and never
executes anything; the scope gate and verifier (deterministic) do that.
"""
