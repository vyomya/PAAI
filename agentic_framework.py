from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from typing import TypedDict
from tool import tools
import json
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
f = open('openAIkey.txt', 'r')
api_key = f.read().strip()
f.close() 
llm = ChatOpenAI(
    api_key=api_key,
    model="gpt-4o-mini",
    temperature=0,
    max_retries=0,
)

# Bind tools to model
llm_with_tools = llm.bind_tools(tools)


# ---- AGENT NODES ----
def orchestrator_node(state):
    """Routes user request to appropriate specialist"""
    user_input = state.get("input", "")
    
    system_prompt = """You are an orchestrator that routes requests to specialists.

Available specialists:
- "summarizer" - for summarizing emails and extracting todos
- "priority" - for prioritizing tasks  
- "email" - for drafting emails

Respond with ONLY a JSON object:
{"destination": "<summarizer|priority|email>", "next_inputs": "<clear instruction>"}"""

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
    """Factory function to create agent nodes"""
    tool_node = ToolNode(tools=tools)
    
    def agent_node(state):
        # Parse input from orchestrator
        orchestrator_output = state.get("output", "")
        try:
            parsed = json.loads(orchestrator_output)
            agent_input = parsed.get("next_inputs", orchestrator_output)
        except:
            agent_input = orchestrator_output
        
        print(f"\n{'='*60}")
        print(f"[{agent_name.upper()}] Input: {agent_input}")
        print(f"{'='*60}\n")
        
        # Create initial messages
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=agent_input)
        ]
        
        tools_used = []
        max_iterations = 10
        
        for iteration in range(max_iterations):
            # Call model
            response = llm_with_tools.invoke(messages)
            messages.append(response)
            
            # Check for tool calls
            if not response.tool_calls:
                # No more tool calls, we're done
                break
            
            print(f"[{agent_name.upper()}] Tool calls: {[tc['name'] for tc in response.tool_calls]}")
            
            # Execute tools
            for tool_call in response.tool_calls:
                tools_used.append(tool_call['name'])
                
                # Find and execute the tool
                tool_name = tool_call['name']
                tool_args = tool_call['args']
                
                tool_result = None
                for tool in tools:
                    if tool.name == tool_name:
                        try:
                            # Convert args to JSON string for our tools
                            tool_input = json.dumps(tool_args)
                            tool_result = tool.func(tool_input)
                            print(f"[{agent_name.upper()}] Tool {tool_name} result: {tool_result[:200]}...")
                        except Exception as e:
                            tool_result = json.dumps({"error": str(e)})
                            print(f"[{agent_name.upper()}] Tool {tool_name} error: {e}")
                        break
                
                if tool_result is None:
                    tool_result = json.dumps({"error": f"Tool {tool_name} not found"})
                
                # Add tool result to messages
                from langchain_core.messages import ToolMessage
                messages.append(ToolMessage(
                    content=tool_result,
                    tool_call_id=tool_call['id']
                ))
        
        # Get final response
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


# Create specialist agents
from datetime import datetime, timedelta
last_week_date = (datetime.now() - timedelta(days=7)).strftime('%Y/%m/%d')

summarizer_agent = create_agent_node(
    "summarizer",
    f"""You are an email summarization specialist with Gmail tools.

**IMPORTANT: You have these tools - USE THEM:**
- FetchEmails: Gets list of emails (returns message IDs)
- GetEmailDetails: Gets full content of a specific email

**YOUR PROCESS:**
1. Call FetchEmails to get email list
2. Call GetEmailDetails for each message ID
3. Summarize and extract todos

**Tool Input Examples:**
- FetchEmails: {{"query": "after:{last_week_date}", "label_ids": ["INBOX"]}}
- GetEmailDetails: {{"msg_id": "actual_message_id"}}

For "last week" use: after:{last_week_date}

After getting emails, provide:
**Summary:** [Overview]
**Todo List:**
- [ ] Task 1 (Priority: High)
- [ ] Task 2 (Priority: Medium)"""
)

priority_agent = create_agent_node(
    "priority",
    """You are a task prioritization specialist.

Prioritize tasks by:
- Urgency (deadlines)
- Importance (impact)
- Dependencies

Output format:
**High Priority:**
1. [task] - Due: [date]

**Medium Priority:**
1. [task]"""
)

email_agent = create_agent_node(
    "email",
    """You are an email drafting specialist.

Create professional emails with:
- Clear subject line
- Appropriate greeting
- Concise body
- Call-to-action
- Professional closing"""
)


# ---- ROUTER ----
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


# ---- EVALUATOR ----
def evaluation_node(state):
    result = state.get("output", "")
    user_goal = state.get("input", "")
    tools_used = state.get("tools_used", [])

    eval_prompt = f"""You are an evaluator.
Does this result satisfy the user's goal?

User goal: {user_goal}
Agent output: {result}

Respond with only "yes" or "no"."""
    
    verdict = llm.invoke(eval_prompt).content.lower()
    is_satisfied = "yes" in verdict

    print(f"\n[EVALUATOR] Satisfied: {is_satisfied}")
    print(f"[EVALUATOR] Tools used: {tools_used}\n")

    return {
        "satisfied": is_satisfied,
        "output": result,
        "tools_used": tools_used
    }


def error_node(state):
    return {
        "output": "Error: evaluation failed. The agent could not complete the task satisfactorily.",
        "tools_used": state.get("tools_used", []),
        "satisfied": False
    }


# ---- STATE ----
class AgentState(TypedDict):
    input: str
    output: str
    tools_used: list
    satisfied: bool


# ---- BUILD GRAPH ----
graph = StateGraph(AgentState)

# Add nodes
graph.add_node("orchestrator", orchestrator_node)
graph.add_node("summarizer_agent", summarizer_agent)
graph.add_node("priority_agent", priority_agent)
graph.add_node("email_agent", email_agent)
graph.add_node("evaluate", evaluation_node)
graph.add_node("error", error_node)

# Set entry point
graph.set_entry_point("orchestrator")

# Conditional routing from orchestrator
graph.add_conditional_edges(
    "orchestrator",
    route_to_agent,
    {
        "summarizer_agent": "summarizer_agent",
        "priority_agent": "priority_agent",
        "email_agent": "email_agent"
    }
)

# All agents go to evaluation
graph.add_edge("summarizer_agent", "evaluate")
graph.add_edge("priority_agent", "evaluate")
graph.add_edge("email_agent", "evaluate")

# Evaluation decides END or error
graph.add_conditional_edges(
    "evaluate",
    lambda s: "END" if s.get("satisfied") else "error",
    {"END": END, "error": "error"}
)

graph.add_edge("error", END)

# Compile
app = graph.compile()


# ---- TEST ----
if __name__ == "__main__":
    
    result = app.invoke({"input": "Summarize last 10 email and provide a todo list."})
    
    print(json.dumps(result, indent=2))