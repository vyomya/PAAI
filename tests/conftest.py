"""
Shared test setup.

Tests stub the LLM with monkeypatch, but the classifier and evaluators in
paai/decisions.py go to TypeSafe's Jev instead whenever TYPESAFE_API_KEY is
set — which it is in a real .env. Then the stubbed answers are ignored, real
API calls are made (slow, and billed), and tests fail depending on whose
machine runs them. Force the LLM path so tests behave the same everywhere.
"""
import pytest

from paai import decisions


@pytest.fixture(autouse=True)
def no_jev(monkeypatch):
    monkeypatch.setattr(decisions, "_client", lambda: None)
    