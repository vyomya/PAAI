"""
Model routing and token accounting.

Two ideas in one module, because they are the same mechanism: every LLM call
goes through invoke() here, which picks a model by task tier and records what
it cost against the calling user.

Tiers
-----
Not every call in the graph needs the same capability. The classifier decides
between three labels. The step evaluator answers a yes/no. The passive
extractor fills a small JSON shape. None of that needs the model that does
multi-step tool calling.

Routing those to a cheaper model is most of the spend, because the cheap calls
are also the frequent ones: a single user turn fires one classifier call, one
planner call, N agent calls, N evaluator calls, one final evaluator and one
extractor. The majority are trivial.
"""
import os
from functools import lru_cache

from langchain_openai import ChatOpenAI

from paai.config import settings

# ── Model tiers ───────────────────────────────────────────────────────────────
# Override per tier with env vars so you can retune without a code change.
TIERS = {
    # Classification, evaluation, extraction: short input, short structured
    # output, no tool calling.
    "cheap": os.environ.get("LLM_CHEAP", "gpt-4o-mini"),

    # Planning and tool-calling agents. Weak models produce malformed tool
    # calls and plans that skip steps, which then costs more in retries than
    # the model saved.
    "standard": os.environ.get("LLM_STANDARD", settings.llm_model or "gpt-4o-mini"),
}

# Approximate USD per 1M tokens. VERIFY against current OpenAI pricing before
# trusting the cost column — these move, and a stale table quietly produces
# wrong numbers rather than an error.
PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o":      {"input": 2.50, "output": 10.00},
}


@lru_cache(maxsize=8)
def _client(model: str, with_tools: bool) -> ChatOpenAI:
    llm = ChatOpenAI(
        api_key=settings.dashscope_api_key,
        model=model,
        temperature=0,
        max_retries=2,          # transient 5xx should not fail a whole agent run
        timeout=60,
    )
    if with_tools:
        from paai.tools import tools
        return llm.bind_tools(tools)
    return llm


def get_llm(tier: str = "standard", with_tools: bool = False) -> ChatOpenAI:
    model = TIERS.get(tier, TIERS["standard"])
    return _client(model, with_tools)


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price = PRICING.get(model)
    if not price:
        return 0.0
    return (
        prompt_tokens * price["input"] / 1_000_000
        + completion_tokens * price["output"] / 1_000_000
    )


# ── Tracked invocation ────────────────────────────────────────────────────────
def invoke(messages, purpose: str, tier: str = "standard", with_tools: bool = False):
    """
    The only way the graph should call a model.

    `purpose` is recorded with the usage row, so you can answer "what is
    actually spending the money" rather than guessing. Expect the answer to be
    the agent nodes and the planner, not the classifier.

    Usage recording is best-effort: a metering failure must never lose a user's
    answer. The limit check happens before the run, not per call, so a run
    already in flight always completes.
    """
    llm = get_llm(tier, with_tools)
    response = llm.invoke(messages)

    try:
        from paai.usage import record_usage

        meta = getattr(response, "usage_metadata", None) or {}
        prompt_tokens = meta.get("input_tokens", 0)
        completion_tokens = meta.get("output_tokens", 0)

        if prompt_tokens or completion_tokens:
            model = TIERS.get(tier, TIERS["standard"])
            record_usage(
                model=model,
                purpose=purpose,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=cost_usd(model, prompt_tokens, completion_tokens),
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[USAGE] recording failed (non-fatal): {exc}")

    return response


# ── Backwards compatibility ───────────────────────────────────────────────────
# graph.py currently does `from paai.llm import llm, llm_with_tools` and calls
# llm.invoke(...) directly. These keep that working during the migration, but
# calls through them are NOT metered — convert the call sites to invoke().
llm = get_llm("standard")
llm_with_tools = get_llm("standard", with_tools=True)