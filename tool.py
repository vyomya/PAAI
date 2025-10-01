from langchain.agents import Tool
# --- Define Tools ---

# 1. Web Search Tool (stubbed, replace with real search API like Tavily or SerpAPI)
def web_search(query: str) -> str:
    return f"Stub: Search results for '{query}'"

# 2. Python Executor Tool
def python_exec(code: str) -> str:
    try:
        return str(eval(code))
    except Exception as e:
        return str(e)

tools = [
    Tool(
        name="WebSearch",
        func=web_search,
        description="Useful for searching information on the web"
    ),
    Tool(
        name="PythonExec",
        func=python_exec,
        description="Useful for running Python code snippets"
    )
]