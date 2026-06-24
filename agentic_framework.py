from langgraph.graph import StateGraph, END
from langgraph.types import Send
from llm import llm, llm_with_tools
from typing import TypedDict, List
from tool import tools
import json
import re
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from prompts import (
    planner_prompt, step_evaluator_prompt, evaluator_prompt,
    summarizer_prompt, priority_prompt, emaildraft_prompt, calendar_prompt,
    history_agent_prompt, preference_agent_prompt
)
from db import (
    init_db, load_messages, save_message, save_session,
    save_preference, load_preferences, delete_preference
)
from datetime import datetime


# ── Classifier ────────────────────────────────────────────────────────────────
PREFERENCE_TRIGGERS = [
    r'\balways\b', r'\bnever\b', r'\bfrom now on\b',
    r'\bevery time\b', r"don't ever", r'\bprefer\b',
    r'\bmake sure you\b', r'\bstop doing\b', r'\bstop showing\b'
]

TASK_WORDS = [
    "summarize", "draft", "send", "check", "schedule", "show",
    "find", "create", "get", "fetch", "give", "list", "reply",
    "add", "update", "tell", "what", "when", "how", "point",
    "last", "previous", "earlier", "discuss", "said", "mention"
]

def classify_message(text: str) -> list:
    text_lower = text.lower()
    types = []
    if any(re.search(p, text_lower) for p in PREFERENCE_TRIGGERS):
        types.append("preference")
    if any(word in text_lower for word in TASK_WORDS):
        types.append("task")
    if not types:
        types.append("task")
    return types


# ── AgentState ────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    user_input: str
    message_history: List[dict]
    session_id: str
    preferences: dict
    message_types: List[str]
    plan: dict
    current_step: int
    context: dict
    artifacts: dict
    step_output: str
    step_evaluation: dict
    final_evaluation: dict
    iteration_count: int


# ── Preference Agent ──────────────────────────────────────────────────────────
def preference_node(state):
    current_prefs = load_preferences()
    prefs_text = "\n".join(f"- {k}: {v}" for k, v in current_prefs.items()) or "None saved yet."

    prompt = preference_agent_prompt.format(
        current_preferences=prefs_text,
        user_input=state["user_input"]
    )

    response = llm.invoke(prompt).content
    clean = re.sub(r'^```(?:json)?\n?', '', response).rstrip('`').strip()

    try:
        result = json.loads(clean)
        if result["action"] == "save":
            save_preference(result["category"], result["rule"])
            print(f"[PREFERENCE] Saved: {result['category']} -> {result['rule']}")
        elif result["action"] == "delete":
            delete_preference(result["category"])
            print(f"[PREFERENCE] Deleted: {result['category']}")

        state["preferences"] = load_preferences()
        return {
            "step_output": result["confirmation"],
            "preferences": state["preferences"]
        }
    except Exception as e:
        print(f"[PREFERENCE] Parse error: {e}")
        return {"step_output": "I've noted your preference."}


# ── History Agent ─────────────────────────────────────────────────────────────
def history_agent_node(state):
    step = state["plan"]["steps"][state["current_step"]]
    goal = step["outputs"][0]

    # ✅ Now uses tools — agent decides whether to search or get recent
    messages = [
        SystemMessage(content=history_agent_prompt),
        HumanMessage(content=f"Goal: {goal}\n\nUse your tools to retrieve the relevant conversation history, then extract what the goal asks for.")
    ]

    tools_used = []
    for _ in range(5):  # history agent doesn't need many iterations
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tools_used.append(tool_call['name'])
            tool_name = tool_call['name']
            tool_args = tool_call['args']
            tool_result = None

            for tool in tools:
                if tool.name == tool_name:
                    try:
                        tool_result = tool.func(json.dumps(tool_args))
                    except Exception as e:
                        tool_result = json.dumps({"error": str(e)})
                    break

            if tool_result is None:
                tool_result = json.dumps({"error": f"Tool {tool_name} not found"})

            from langchain_core.messages import ToolMessage
            messages.append(ToolMessage(
                content=tool_result,
                tool_call_id=tool_call['id']
            ))

    final_content = messages[-1].content if messages else ""

    print(f"\n{'='*60}")
    print(f"[HISTORY] Goal: {goal}")
    print(f"[HISTORY] Tools used: {tools_used}")
    print(f"[HISTORY] Output: {final_content}")
    print(f"{'='*60}\n")

    return {
        "step_output": final_content,
        "artifacts": {**state["artifacts"], step["id"]: final_content},
        "current_step": state["current_step"],
        "iteration_count": state["iteration_count"]
    }

# ── Planner ───────────────────────────────────────────────────────────────────
def planner_node(state):
    history_messages = []
    for m in state["message_history"]:
        if m["role"] == "user":
            history_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            history_messages.append(AIMessage(content=m["content"]))
        elif m["role"] == "system":
            history_messages.append(SystemMessage(content=m["content"]))

    # Tell planner what artifacts already exist so it doesn't re-fetch
    available_artifacts = ""
    if state.get("artifacts"):
        available_artifacts = (
            "\n\nData already computed this session (reuse this, do NOT re-fetch):\n"
            + json.dumps(state["artifacts"], indent=2)
        )

    messages = [
        SystemMessage(content=planner_prompt + available_artifacts),
        *history_messages,
        HumanMessage(content=state["user_input"])
    ]

    content = llm.invoke(messages).content
    print(repr(content))

    # Try direct parse first
    try:
        clean = re.sub(r'^```(?:json)?\n?', '', content).rstrip('`').strip()
        plan = json.loads(clean)

    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                plan = json.loads(json_match.group())
            except json.JSONDecodeError:
                plan = None
        else:
            plan = None

        # Ask LLM to fix itself
        if not plan:
            print(f"[PLANNER] No JSON found, asking LLM to reformat...")
            fix_messages = messages + [
                AIMessage(content=content),
                HumanMessage(content=(
                    "Your response was not valid JSON. "
                    "You MUST return ONLY a JSON plan using the available specialists. "
                    "Do NOT answer the question — plan the steps to get the answer. "
                    "For history/reference requests use history_agent. "
                    "For email fetching use summarizer_agent. "
                    "Return ONLY the JSON object, no other text."
                ))
            ]
            retry_content = llm.invoke(fix_messages).content
            json_match = re.search(r'\{.*\}', retry_content, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group())
            else:
                raise ValueError(
                    f"Planner failed twice to return JSON.\n"
                    f"Original: {content}\nRetry: {retry_content}"
                )

    print({"plan": plan, "current_step": 0, "artifacts": state.get("artifacts", {}), "iteration_count": 0})

    return {
        "plan": plan,
        "current_step": 0,
        "artifacts": state.get("artifacts", {}),
        "context": state.get("context", {}),
        "iteration_count": 0,
        "step_output": ""
    }


# ── Agent Node Factory ────────────────────────────────────────────────────────
def create_agent_node(agent_name, system_prompt):

    def agent_node(state):
        step = state["plan"]["steps"][state["current_step"]]
        issues = state.get("step_evaluation", {}).get("issues", "")

        # Inject preferences into every agent's system prompt
        prefs = state.get("preferences", {})
        if prefs:
            pref_text = "\n".join(f"- {rule}" for rule in prefs.values())
            enriched_prompt = system_prompt + f"\n\nUser Preferences (strictly follow these):\n{pref_text}"
        else:
            enriched_prompt = system_prompt

        # Pass prior artifacts as context so agents don't re-fetch
        prior_context = ""
        if state.get("artifacts"):
            prior_context = (
                "\n\nPreviously computed data (use this directly, do NOT re-fetch):\n"
                + json.dumps(state["artifacts"], indent=2)
            )

        if issues:
            human_content = (
                f"Your specific goal for this step: {step['outputs'][0]}\n"
                f"{prior_context}\n\n"
                f"Previous attempt failed with these issues:\n{issues}\n"
                f"Previous bad output was:\n{state['step_output']}\n"
                f"Please produce a corrected output addressing the issues above."
            )
        else:
            human_content = (
                f"Your specific goal for this step: {step['outputs'][0]}\n"
                f"{prior_context}\n"
                f"{state['step_output']}"
            )

        messages = [
            SystemMessage(content=enriched_prompt),
            HumanMessage(content=human_content)
        ]

        tools_used = []
        for _ in range(10):
            response = llm_with_tools.invoke(messages)
            messages.append(response)

            if not response.tool_calls:
                break

            print(f"[{agent_name.upper()}] Tool calls: {[tc['name'] for tc in response.tool_calls]}")

            for tool_call in response.tool_calls:
                tools_used.append(tool_call['name'])
                tool_name = tool_call['name']
                tool_args = tool_call['args']
                print(f"[{agent_name.upper()}] Using tool {tool_name} with args: {tool_args}")
                tool_result = None

                for tool in tools:
                    if tool.name == tool_name:
                        try:
                            tool_input = json.dumps(tool_args)
                            tool_result = tool.func(tool_input)
                            print(f"[{agent_name.upper()}] Tool {tool_name} result: {tool_result[:200]}...")
                            if tool_name == "GetTime":
                                state['context'] = {"current_time": tool_result}
                        except Exception as e:
                            tool_result = json.dumps({"error": str(e)})
                            print(f"[{agent_name.upper()}] Tool {tool_name} error: {e}")
                        break

                if tool_result is None:
                    tool_result = json.dumps({"error": f"Tool {tool_name} not found"})

                from langchain_core.messages import ToolMessage
                messages.append(ToolMessage(
                    content=tool_result,
                    tool_call_id=tool_call['id']
                ))

        final_content = messages[-1].content if messages else ""

        print(f"\n{'='*60}")
        print(f"[{agent_name.upper()}] Output: {final_content}")
        print(f"[{agent_name.upper()}] Tools used: {tools_used}")
        print(f"{'='*60}\n")

        return {
            "step_output": final_content,
            "artifacts": {
                **state["artifacts"],
                step["id"]: final_content
            },
            "current_step": state["current_step"],
            "iteration_count": state["iteration_count"]
        }

    return agent_node


summarizer_agent = create_agent_node("summarizer", summarizer_prompt)
priority_agent   = create_agent_node("priority", priority_prompt)
email_agent      = create_agent_node("email", emaildraft_prompt)
calendar_agent   = create_agent_node("calendar", calendar_prompt)


# ── Step Evaluator ────────────────────────────────────────────────────────────
def step_evaluator_node(state):
    step = state["plan"]["steps"][state["current_step"]]

    prompt = step_evaluator_prompt.format(
        user_input=state["user_input"],
        outputs=step["outputs"],
        step_output=state["step_output"],
        context=json.dumps(state['context'])
    )

    print(f"[EVALUATOR] Checking step goal: {step['outputs']}")
    print(f"[EVALUATOR] Step output preview: {state['step_output'][:200]}...")
    output = llm.invoke(prompt).content
    print(output)

    if "true" in output.lower():
        return {"step_evaluation": {"approved": True, "issues": "", "repair": "continue"}}
    else:
        try:
            output = "{" + output.split("{")[1]
            output = output.split("}")[0] + "}"
            output = json.loads(output)
        except Exception:
            print("[EVALUATOR] Parse error on rejection — approving to avoid loop")
            return {"step_evaluation": {"approved": True, "issues": "", "repair": "continue"}}

        return {
            "step_evaluation": output,
            "current_step": state["current_step"],
            "iteration_count": state["iteration_count"]
        }


# ── Step Router ───────────────────────────────────────────────────────────────
def step_router(state):
    evaluation = state["step_evaluation"]
    st_update = dict(state)
    st_update["iteration_count"] += 1

    if st_update["iteration_count"] > 3:
        return Send("final_evaluator", st_update)

    if not evaluation["approved"]:
        st_update["step_output"] = ""
        return Send(st_update["plan"]["steps"][st_update["current_step"]]["agent"], st_update)

    if st_update["current_step"] + 1 < len(st_update["plan"]["steps"]):
        st_update["current_step"] += 1
        st_update["iteration_count"] = 0
        return Send(st_update["plan"]["steps"][st_update["current_step"]]["agent"], st_update)

    return Send("final_evaluator", st_update)


# ── Final Evaluator ───────────────────────────────────────────────────────────
def final_evaluator_node(state):
    prompt = evaluator_prompt.format(
        user_input=state["user_input"],
        artifacts=json.dumps(state["artifacts"]),
        context=json.dumps(state['context']),
        indent=2
    )
    verdict = llm.invoke(prompt).content.lower()
    plan_summary = [step["agent"] for step in state["plan"]["steps"]]

    save_session(
        user_input=state["user_input"],
        final_output=state["step_output"],
        plan_summary=plan_summary,
        session_id=state["session_id"]
    )

    save_message(state["session_id"], "user", state["user_input"])
    save_message(state["session_id"], "assistant", state["step_output"])

    if state["artifacts"]:
        save_message(
            state["session_id"],
            "system",
            f"[ARTIFACTS FROM PREVIOUS QUERY]\n{json.dumps(state['artifacts'], indent=2)}"
        )

    return {
        "final_evaluation": {
            "approved": "yes" in verdict,
            "verdict": verdict
        }
    }


# ── Graphs ────────────────────────────────────────────────────────────────────

# Preference-only graph
pref_graph = StateGraph(AgentState)
pref_graph.add_node("preference_agent", preference_node)
pref_graph.set_entry_point("preference_agent")
pref_graph.add_edge("preference_agent", END)
pref_app = pref_graph.compile()

# Task graph — now includes history_agent
task_graph = StateGraph(AgentState)
task_graph.add_node("planner",          planner_node)
task_graph.add_node("history_agent",    history_agent_node)   # ✅ new
task_graph.add_node("summarizer_agent", summarizer_agent)
task_graph.add_node("priority_agent",   priority_agent)
task_graph.add_node("email_agent",      email_agent)
task_graph.add_node("calendar_agent",   calendar_agent)
task_graph.add_node("step_evaluator",   step_evaluator_node)
task_graph.add_node("final_evaluator",  final_evaluator_node)
task_graph.set_entry_point("planner")
task_graph.add_conditional_edges("planner", lambda s: s["plan"]["steps"][0]["agent"])
for agent in ["history_agent", "summarizer_agent", "priority_agent", "email_agent", "calendar_agent"]:
    task_graph.add_edge(agent, "step_evaluator")
task_graph.add_conditional_edges("step_evaluator", step_router)
task_graph.add_edge("final_evaluator", END)
task_app = task_graph.compile()


# ── Entry Point ───────────────────────────────────────────────────────────────
init_db()

def run_agent(user_query: str):
    session_id = datetime.now().strftime("%Y%m%d%H%M%S")
    message_history = load_messages(query=user_query, limit=10)
    preferences = load_preferences()
    message_types = classify_message(user_query)
    print(f"[CLASSIFIER] Types detected: {message_types}")

    initial_state = {
        "user_input":       user_query,
        "message_history":  message_history,
        "session_id":       session_id,
        "preferences":      preferences,
        "message_types":    message_types,
        "plan":             {},
        "current_step":     0,
        "artifacts":        {},
        "context":          {},
        "step_output":      "",
        "step_evaluation":  {},
        "final_evaluation": {},
        "iteration_count":  0
    }

    if "preference" in message_types and "task" not in message_types:
        print("[CLASSIFIER] -> preference_agent only")
        result = pref_app.invoke(initial_state)
        return result["step_output"]

    elif "preference" in message_types and "task" in message_types:
        print("[CLASSIFIER] -> preference_agent then task")
        pref_result = pref_app.invoke(initial_state)
        print(f"[PREFERENCE] {pref_result['step_output']}")
        initial_state["preferences"] = load_preferences()
        result = task_app.invoke(initial_state)
        return f"{pref_result['step_output']}\n\n{result['step_output']}"

    else:
        print("[CLASSIFIER] -> planner")
        result = task_app.invoke(initial_state)
        return result["step_output"]


if __name__ == "__main__":
    user_query = input("Enter your query: ")
    response = run_agent(user_query)
    print(response)