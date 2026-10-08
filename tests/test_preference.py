"""
A preference saved for one agent must reach that agent's prompt.

Regression for: "Set the follow ups on my job application as High Priority"
was saved with scope "priority_agent", but the priority agent only looked for
"priority" and "global", so the rule never reached it. Being an inferred
(implicit) preference, it was also only ever a soft suggestion.
"""
import json
import uuid

from paai import graph
from paai.context import user_context
from paai.db import get_or_create_user, load_preferences

RULE = "Treat follow-ups on job applications as High priority"


class _Reply:
    def __init__(self, content):
        self.content = content
        self.tool_calls = []
        self.usage_metadata = {}


def _priority_prompt(monkeypatch, preferences):
    captured = {}

    def fake_invoke(messages, purpose, tier="standard", with_tools=False):
        captured["system"] = messages[0].content
        return _Reply("done")

    monkeypatch.setattr(graph, "invoke", fake_invoke)
    graph.priority_agent({
        "plan": {"steps": [{"id": "1", "agent": "priority_agent", "outputs": ["rank"]}]},
        "current_step": 0, "preferences": preferences, "artifacts": {},
        "step_output": "", "iteration_count": 0, "context": {},
    })
    return captured["system"]


def test_agent_scoped_preference_reaches_its_agent(monkeypatch):
    prompt = _priority_prompt(monkeypatch, {
        "job_followups": {"rule": RULE, "scope": "priority_agent", "confidence": 0.9,
                          "source": "explicit", "reinforcement_count": 1},
    })
    rules = prompt.split("Rules (always follow):")[1]
    assert RULE in rules


def test_other_agents_preferences_stay_out(monkeypatch):
    prompt = _priority_prompt(monkeypatch, {
        "tone": {"rule": "Write formally", "scope": "email_agent", "confidence": 0.9,
                 "source": "explicit", "reinforcement_count": 3},
    })
    assert "Write formally" not in prompt


def test_inferred_preference_is_soft_until_reinforced(monkeypatch):
    prompt = _priority_prompt(monkeypatch, {
        "job_followups": {"rule": RULE, "scope": "priority_agent", "confidence": 0.8,
                          "source": "implicit", "reinforcement_count": 1},
    })
    assert "Rules (always follow)" not in prompt
    assert RULE in prompt.split("Soft preferences")[1]


def test_direct_instruction_in_a_task_turn_sticks(monkeypatch):
    """End to end: said once in a task message, applied as a rule next time."""
    priority_prompts = []
    turn = {"n": 1}

    def fake_invoke(messages, purpose, tier="standard", with_tools=False):
        if purpose == "classifier":
            return _Reply(json.dumps({"types": ["task"], "has_correction": False,
                                      "contradiction_strength": "none", "reasoning": ""}))
        if purpose == "planner":
            return _Reply(json.dumps({"steps": [
                {"id": "1", "agent": "priority_agent", "outputs": ["Make a to-do list"]}]}))
        if purpose == "step_eval":
            return _Reply("true")
        if purpose == "extractor":
            signals = [{"category": "job_followup_priority", "rule": RULE,
                        "scope": "priority_agent", "confidence": 0.8, "source": "explicit",
                        "contradiction": False, "contradiction_strength": "none"}]
            return _Reply(json.dumps({"signals": signals if turn["n"] == 1 else []}))
        if purpose == "agent:priority":
            priority_prompts.append(messages[0].content)
        return _Reply("ok")

    monkeypatch.setattr(graph, "invoke", fake_invoke)
    monkeypatch.setattr("paai.llm.invoke", fake_invoke)

    user = get_or_create_user(f"pref-scope-{uuid.uuid4().hex[:8]}@test.local")
    with user_context(user):
        graph.run_agent("Set the follow ups on my job application as High Priority")
        saved = load_preferences(user)["job_followup_priority"]
        assert saved["source"] == "explicit" and saved["confidence"] >= 0.7

        turn["n"] = 2
        graph.run_agent("summarize yesterday's mail and give me a to-do list")

    assert RULE in priority_prompts[-1].split("Rules (always follow):")[1]