"""
A retried step must actually try again.

Regression: on a retry, the step's own rejected output was handed back to the
agent as "Previously computed data (use this directly, do NOT re-fetch)", so
the summarizer re-worded the same six emails without calling a single tool
(logs: "[SUMMARIZER] Tools used: []") and failed every retry. The History
Agent's retries never saw the evaluator's feedback at all.
"""
import json
import uuid

from paai import graph
from paai.context import user_context
from paai.db import get_or_create_user


class _Reply:
    def __init__(self, content):
        self.content = content
        self.tool_calls = []
        self.usage_metadata = {}


def _run(monkeypatch, steps, evals, agent_outputs):
    """Run the real graph with a scripted LLM; return the human message each agent got."""
    evals, seen = iter(evals), {}

    def fake_invoke(messages, purpose, tier="standard", with_tools=False):
        if purpose == "classifier":
            return _Reply(json.dumps({"types": ["task"], "has_correction": False,
                                      "contradiction_strength": "none", "reasoning": ""}))
        if purpose == "planner":
            return _Reply(json.dumps({"steps": steps}))
        if purpose in ("step_eval", "step_eval_repair"):
            return _Reply(next(evals))
        if purpose == "extractor":
            return _Reply('{"signals": []}')
        if purpose.startswith("agent:") or purpose == "history":
            seen.setdefault(purpose, []).append(messages[1].content)
            outs = agent_outputs[purpose]
            return _Reply(outs[min(len(seen[purpose]), len(outs)) - 1])
        return _Reply("ok")

    monkeypatch.setattr(graph, "invoke", fake_invoke)
    monkeypatch.setattr("paai.llm.invoke", fake_invoke)
    user = get_or_create_user(f"retry-{uuid.uuid4().hex[:8]}@test.local")
    with user_context(user):
        graph.run_agent("summarize the last ten emails")
    return seen


def test_retry_starts_over_instead_of_rewording(monkeypatch):
    seen = _run(
        monkeypatch,
        steps=[{"id": "1", "agent": "summarizer_agent", "outputs": ["Summarize the last ten emails"]}],
        evals=['{"approved": false, "issues": "Only six of the ten emails", "repair": "retry"}', "true"],
        agent_outputs={"agent:summarizer": ["SIX EMAILS", "TEN EMAILS"]},
    )
    first, retry = seen["agent:summarizer"][:2]
    assert "SIX EMAILS" not in first
    assert "Only six of the ten emails" in retry          # the evaluator's reason
    assert "SIX EMAILS" in retry.split("Previous output:")[1]
    assert "do NOT re-fetch" not in retry                  # no longer told to reuse it
    assert "call your tools" in retry


def test_next_step_still_gets_earlier_results(monkeypatch):
    seen = _run(
        monkeypatch,
        steps=[{"id": "1", "agent": "summarizer_agent", "outputs": ["Summarize mail"]},
               {"id": "2", "agent": "priority_agent", "outputs": ["Make a to-do list"]}],
        evals=["true", "true"],
        agent_outputs={"agent:summarizer": ["TEN EMAILS"], "agent:priority": ["TODO"]},
    )
    priority_msg = seen["agent:priority"][0]
    assert "TEN EMAILS" in priority_msg.split("Results from earlier steps")[1]


def test_history_retry_gets_the_feedback(monkeypatch):
    seen = _run(
        monkeypatch,
        steps=[{"id": "1", "agent": "history_agent", "outputs": ["Recall the forwarded email"]}],
        evals=['{"approved": false, "issues": "Did not find the email", "repair": "retry"}', "true"],
        agent_outputs={"history": ["NOT FOUND", "FOUND"]},
    )
    assert "Did not find the email" in seen["history"][1]