from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, create_react_agent
from langchain_community.chat_models import ChatOllama
from tool import tools
from prompts import priority_prompt, summarizer_prompt, emaildraft_prompt, orchestrator_prompt
from typing import TypedDict

from langchain_openai import ChatOpenAI
llm = ChatOpenAI(
    api_key="ollama",
    model="llama3:8b",
    base_url="http://localhost:11434/v1",
)
# Define specialized agents
priority_agent = create_react_agent(
    model=llm,
    prompt=priority_prompt,
    tools=tools,

)

email_agent = create_react_agent(
    model=llm,
    prompt=emaildraft_prompt,
    tools=tools,

)

summarizer_agent = create_react_agent(
    model=llm,
    prompt=summarizer_prompt,
    tools=tools
)

# Define orchestrator
orchestrator = create_react_agent(
    model=llm,
    prompt=orchestrator_prompt,
    tools=[]# Orchestrator does not use tools directly
)


def evaluation_node(state):
    result = state["last_output"]
    user_goal = state["user_goal"]
    llm = llm
    eval_prompt = f"""
    You are an Evaluator.
    Determine if this result satisfies the user's goal.
    User goal: {user_goal}
    Agent output: {result}
    Respond with 'yes' or 'no'.
    """
    verdict = llm.invoke(eval_prompt).content.lower()
    return {"satisfied": "yes" in verdict}
class AgentState(TypedDict):
    input: str
    output: str
# Create flow graph
graph = StateGraph(
    state_schema=AgentState
)
graph.add_node("orchestrator", orchestrator)
graph.add_node("priority_agent", priority_agent)
graph.add_node("email_agent", email_agent)
graph.add_node("summarizer_agent", summarizer_agent)
graph.add_node("evaluate", evaluation_node)

graph.add_edge("orchestrator", "priority_agent")
graph.add_edge("orchestrator", "email_agent")
graph.add_edge("orchestrator", "summarizer_agent")
graph.add_edge("priority_agent", "evaluate")
graph.add_edge("email_agent", "evaluate")
graph.add_edge("summarizer_agent", "evaluate")
graph.add_conditional_edges(
    "evaluate",
    lambda state: "END" if state["satisfied"] else "orchestrator",
    {"END": END, "orchestrator": "orchestrator"}
)

graph.set_entry_point("orchestrator")

app = graph.compile()
result = app.invoke({"input": "Summarize last week's email and provide a todo list."})
print(result)

