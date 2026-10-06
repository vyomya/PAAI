"""
/agent must return the plan ledger the chat UI renders ("How it got there").

It always returned plan=[] because run_agent never surfaced the plan or the
step evaluations, so the ledger never appeared.
"""
import json
import uuid

from paai import graph
from paai.context import user_context
from paai.db import get_or_create_user
from paai.graph import build_plan_ledger


class _Reply:
    def __init__(self, content):
        self.content = content
        self.tool_calls = []
        self.usage_metadata = {}


def test_build_plan_ledger_statuses():
    plan = {"steps": [
        {"id": "1", "agent": "summarizer_agent", "outputs": ["fetch mail"]},
        {"id": "2", "agent": "priority_agent", "outputs": ["rank tasks"]},
        {"id": "3", "agent": "email_agent", "outputs": ["draft reply"]},
    ]}
    log = [
        {"step_id": "1", "approved": True, "issues": ""},
        {"step_id": "2", "approved": False, "issues": "missing deadlines"},
        {"step_id": "2", "approved": False, "issues": "still missing"},
    ]
    ledger = build_plan_ledger(plan, log)
    assert [r["status"] for r in ledger] == ["done", "failed", "failed"]
    assert ledger[1]["note"] == "still missing"
    assert ledger[2]["note"].startswith("Skipped")


def test_run_agent_returns_ledger(monkeypatch):
    evals = iter(["true", '{"approved": false, "issues": "too vague", "repair": "retry"}', "true"])

    def fake_invoke(messages, purpose, tier="standard", with_tools=False):
        if purpose == "classifier":
            return _Reply(json.dumps({"types": ["task"], "has_correction": False,
                                      "contradiction_strength": "none", "reasoning": ""}))
        if purpose == "planner":
            return _Reply(json.dumps({"steps": [
                {"id": "1", "agent": "history_agent", "outputs": ["recall the list"]},
                {"id": "2", "agent": "priority_agent", "outputs": ["rank it"]},
            ]}))
        if purpose == "step_eval":
            return _Reply(next(evals))
        if purpose == "extractor":
            return _Reply('{"signals": []}')
        return _Reply("ok")

    monkeypatch.setattr(graph, "invoke", fake_invoke)
    monkeypatch.setattr("paai.llm.invoke", fake_invoke)

    user = get_or_create_user(f"ledger-{uuid.uuid4().hex[:8]}@test.local")
    with user_context(user):
        answer, session_id, plan = graph.run_agent("rank yesterday's list")

    assert answer == "ok" and session_id
    assert [(p["agent"], p["status"]) for p in plan] == [
        ("history_agent", "done"),
        ("priority_agent", "retried"),
    ]