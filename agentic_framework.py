from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import initialize_agent, Tool

# --- Define LLM ---
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# --- Specialist Agents ---

research_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are ResearchAgent. Answer using only the WebSearch tool."),
    ("human", "{input}")
])

coder_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are CoderAgent. Answer using only the PythonExec tool."),
    ("human", "{input}")
])

research_agent = initialize_agent(
    tools=[tools[0]],  # WebSearch
    llm=llm,
    agent="chat-conversational-react-description",
    verbose=True
)

coder_agent = initialize_agent(
    tools=[tools[1]],  # PythonExec
    llm=llm,
    agent="chat-conversational-react-description",
    verbose=True
)

# --- Orchestrator Agent ---
def orchestrator(task: str) -> str:
    if "search" in task.lower():
        return research_agent.run(task)
    elif "calculate" in task.lower() or "python" in task.lower():
        return coder_agent.run(task)
    else:
        return "Orchestrator: I don't know which agent to use."

# --- Example Run ---
print(orchestrator("search latest AI trends"))
print(orchestrator("calculate 5+12"))
