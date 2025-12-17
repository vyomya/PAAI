from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from llm import llm, llm_with_tools
from typing import TypedDict
from tool import tools
import json
from langchain_core.messages import  HumanMessage, SystemMessage
from prompts import orchestrator_prompt, summarizer_prompt, priority_prompt, emaildraft_prompt

def orchestrator_node(state):
    """Routes user request to appropriate specialist"""
    evaluation_feedback = state.get("evaluation_input", "")
    user_input = state.get("user_input", "")
    if evaluation_feedback!="":
        output = state.get("output", "")
        user_input = f"""
        Previous attempt was insufficient.
        
        Original input: {user_input}
        Previous output: {output}
        
        Evaluation feedback:
        {evaluation_feedback}
        
        Please provide an improved response that addresses the feedback.
        """
    system_prompt = orchestrator_prompt
    print(user_input)
    print(evaluation_feedback)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input)
    ]
    
    response = llm.invoke(messages)
    
    print(f"\n[ORCHESTRATOR] Response: {response.content}\n")
    
    return {
        "output": response.content,
        "tools_used": []
    }


def create_agent_node(agent_name, system_prompt):
    
    tool_node = ToolNode(tools=tools)
    
    def agent_node(state):

        orchestrator_output = state.get("output", "")
        try:
            parsed = json.loads(orchestrator_output)
            agent_input = parsed.get("next_inputs", orchestrator_output)
        except:
            agent_input = orchestrator_output
        
        print(f"\n{'='*60}")
        print(f"[{agent_name.upper()}] Input: {agent_input}")
        print(f"{'='*60}\n")
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=agent_input)
        ]
        
        tools_used = []
        max_iterations = 10
        
        for _ in range(max_iterations):
            
            response = llm_with_tools.invoke(messages)
            messages.append(response)
            
            if not response.tool_calls:
                
                break
            
            print(f"[{agent_name.upper()}] Tool calls: {[tc['name'] for tc in response.tool_calls]}")
            
            for tool_call in response.tool_calls:
                tools_used.append(tool_call['name'])
                
                tool_name = tool_call['name']
                tool_args = tool_call['args']
                
                tool_result = None
                for tool in tools:
                    if tool.name == tool_name:
                        try:
                            tool_input = json.dumps(tool_args)
                            tool_result = tool.func(tool_input)
                            print(f"[{agent_name.upper()}] Tool {tool_name} result: {tool_result[:200]}...")
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
            "output": final_content,
            "tools_used": tools_used
        }
    
    return agent_node


summarizer_agent = create_agent_node(
    "summarizer",
    summarizer_prompt
)

priority_agent = create_agent_node(
    "priority",
    priority_prompt
)

email_agent = create_agent_node(
    "email",
    emaildraft_prompt
)


def route_to_agent(state):
    """Route to appropriate agent based on orchestrator output"""
    output = state.get("output", "")
    
    print(f"\n[ROUTER] Routing based on: {output}\n")
    
    try:
        parsed = json.loads(output)
        destination = parsed.get("destination", "").lower()
        
        if "summariz" in destination:
            return "summarizer_agent"
        elif "priority" in destination or "prioritiz" in destination:
            return "priority_agent"
        elif "email" in destination or "draft" in destination:
            return "email_agent"
    except:
        output_lower = output.lower()
        if "summariz" in output_lower:
            return "summarizer_agent"
        elif "priority" in output_lower:
            return "priority_agent"
        elif "email" in output_lower:
            return "email_agent"
    
    print("[ROUTER] Defaulting to summarizer_agent\n")
    return "summarizer_agent"


def evaluation_node(state):
    result = state.get("output", "")
    user_goal = state.get("user_input", "")
    tools_used = state.get("tools_used", [])
    iteration_count = state.get("iteration_count")
    eval_prompt = f"""You are an evaluator.
Does this result satisfy the user's goal?
Make your decision based on the following criteria:
    1. Completeness: Does the result fully address the user's request? Does it answer/ fulfill all parts of the request?
    2. Accuracy: Is the information provided correct and relevant to the user's goal?

User goal: {user_goal}
Agent output: {result}

Respond with "yes" or "no" . 
If the result does not satisfy the user's goal =>
    Reframe the request and provide feedback on what is missing or incorrect.
    Make sure to include the incomplete or missing part of original user goal.
    Also include the agent's output that might be useful for next part in your feedback.
"""
    
    verdict = llm.invoke(eval_prompt).content.lower()
    is_satisfied = "yes" in verdict
    print(f"\n[EVALUATOR] Verdict: {verdict}")
    print(f"\n[EVALUATOR] Satisfied: {is_satisfied}")
    print(f"[EVALUATOR] Tools used: {tools_used}\n")
    
    return {
        "satisfied": is_satisfied,
        "evaluation_input": verdict,
        "output": result,
        "tools_used": tools_used,
        "iteration_count": iteration_count + 1
    }


def error_node(state):
    return {
        "output": "Error: evaluation failed. The agent could not complete the task satisfactorily.",
        "tools_used": state.get("tools_used", []),
        "satisfied": False
    }

class AgentState(TypedDict):
    user_input: str
    evaluation_input: str = None
    output: str
    tools_used: list
    satisfied: bool
    iteration_count: int = 0


graph = StateGraph(AgentState)

# Add nodes
graph.add_node("orchestrator", orchestrator_node)
graph.add_node("summarizer_agent", summarizer_agent)
graph.add_node("priority_agent", priority_agent)
graph.add_node("email_agent", email_agent)
graph.add_node("evaluate", evaluation_node)
graph.add_node("error", error_node)

graph.set_entry_point("orchestrator")

graph.add_conditional_edges(
    "orchestrator",
    route_to_agent,
    {
        "summarizer_agent": "summarizer_agent",
        "priority_agent": "priority_agent",
        "email_agent": "email_agent"
    }
)

graph.add_edge("summarizer_agent", "evaluate")
graph.add_edge("priority_agent", "evaluate")
graph.add_edge("email_agent", "evaluate")

graph.add_conditional_edges(
    "evaluate",
    lambda s: "END" if (s.get("satisfied") or s.get("iteration_count")>=3) else "orchestrator",
    {
        "END": END,
        "orchestrator": "orchestrator",
        "error": "error"
    }
)

graph.add_edge("error", END)

app = graph.compile()


# ---- TEST ----
if __name__ == "__main__":
    
    result = app.invoke({"user_input": "Summarize last 10 email and provide a prioritized todo list.","iteration_count":0})
    
    print(json.dumps(result, indent=2))