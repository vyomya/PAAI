from langgraph.graph import StateGraph, END
from langgraph.types import Send
from llm import llm, llm_with_tools
from typing import TypedDict, List
from tool import tools
import json
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from prompts import planner_prompt, step_evaluator_prompt, evaluator_prompt, summarizer_prompt, priority_prompt, emaildraft_prompt, calendar_prompt
import re
from db import init_db, load_messages, save_message, save_session
from datetime import datetime

class AgentState(TypedDict):
    user_input: str
    message_history: List[dict]
    session_id: str
    plan: dict
    current_step: int
    context: dict
    artifacts: dict
    step_output: str
    step_evaluation: dict
    final_evaluation: dict
    iteration_count: int

def planner_node(state):
    history_messages = []
    for m in state["message_history"]:
        if m["role"] == "user":
            history_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            history_messages.append(AIMessage(content=m["content"]))
        elif m["role"] == "system":
            history_messages.append(SystemMessage(content=m["content"]))

    messages = [
        SystemMessage(content=planner_prompt),
        *history_messages,
        HumanMessage(content=state["user_input"])
    ]

    content = llm.invoke(messages).content
    clean = re.sub(r'^```(?:json)?\n?', '', content).rstrip('`').strip()
    plan = json.loads(clean)

    print({"plan": plan,
    "current_step": 0,
    "artifacts": {},
    "iteration_count": 0})

    return {
        "plan": plan,
        "current_step": 0,
        "artifacts": {},
        "context": {},
        "iteration_count": 0,
        "step_output":""
    }

def create_agent_node(agent_name, system_prompt):

    def agent_node(state):
        step = state["plan"]["steps"][state["current_step"]]
        issues = state.get("step_evaluation", {}).get("issues", "")

        if issues:
            human_content = (
                f"{step['outputs'][0]}\n\n"
                f"Previous attempt failed with these issues:\n{issues}\n"
                f"Previous bad output was:\n{state['step_output']}\n"
                f"Please produce a corrected output."
            )
        else:
            human_content = step["outputs"][0] + "\n" + state["step_output"]

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_content)]
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
                                state['context']= {"current_time":tool_result}
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
            "current_step":state["current_step"],
            "iteration_count":state["iteration_count"]
        }
    
    return agent_node

summarizer_agent = create_agent_node("summarizer", summarizer_prompt)
priority_agent = create_agent_node("priority", priority_prompt)
email_agent = create_agent_node("email", emaildraft_prompt)
calendar_agent = create_agent_node("calendar", calendar_prompt)

def step_evaluator_node(state):
    step = state["plan"]["steps"][state["current_step"]]

    prompt = step_evaluator_prompt.format(user_input=state["user_input"],outputs=step["outputs"],step_output=state["step_output"],context=json.dumps(state['context']))
    print(state["user_input"])
    print(state["step_output"])
    output = llm.invoke(prompt).content
    print(output)
    if "true" in output.lower():
        return {"step_evaluation": {"approved": True, "issues": "", "repair": "continue"}}
    else:
        output = "{" + output.split("{")[1]
        output = output.split("}")[0] + "}"
        output = json.loads(output)
        return {"step_evaluation": output, "current_step":state["current_step"],
            "iteration_count":state["iteration_count"]}



def step_router(state):
    evaluation = state["step_evaluation"]
    st_update = dict(state)
    st_update["iteration_count"]+=1
    
    if st_update["iteration_count"] > 3:
        return Send("final_evaluator", st_update)

    if not evaluation["approved"]:
        st_update["step_output"] = ""
        return Send(st_update["plan"]["steps"][st_update["current_step"]]["agent"], st_update)

    if st_update["current_step"] + 1 < len(st_update["plan"]["steps"]):
        st_update["current_step"] +=1
        return Send(st_update["plan"]["steps"][st_update["current_step"]]["agent"], st_update)

    return Send("final_evaluator", st_update)


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


graph = StateGraph(AgentState)

graph.add_node("planner", planner_node)
graph.add_node("summarizer_agent", summarizer_agent)
graph.add_node("priority_agent", priority_agent)
graph.add_node("email_agent", email_agent)
graph.add_node("calendar_agent", calendar_agent)
graph.add_node("step_evaluator", step_evaluator_node)
graph.add_node("final_evaluator", final_evaluator_node)

graph.set_entry_point("planner")

graph.add_conditional_edges(
    "planner",
    lambda s: s["plan"]["steps"][0]["agent"]
)

for agent in ["summarizer_agent", "priority_agent", "email_agent", "calendar_agent"]:
    graph.add_edge(agent, "step_evaluator")

graph.add_conditional_edges("step_evaluator", step_router)
graph.add_edge("final_evaluator", END)

app = graph.compile()

init_db()

def run_agent(user_query: str):
    session_id = datetime.now().strftime("%Y%m%d%H%M%S")
    message_history = load_messages(limit=20)

    initial_state = {
        "user_input": user_query,
        "message_history": message_history,
        "session_id": session_id,
        "plan": {},
        "current_step": 0,
        "artifacts": {},
        "context":{},
        "step_output": "",
        "step_evaluation": {},
        "final_evaluation": {},
        "iteration_count": 0
    }

    result = app.invoke(initial_state)
    return result["step_output"]

if __name__ == "__main__":
    user_query = input("Enter your query: ")
    response = run_agent(user_query)
    print(json.dumps(response, indent=2))