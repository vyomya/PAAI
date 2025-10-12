from langchain.agents import Tool

from gmail_api import get_message, list_messages
# --- Define Tools ---

# 1. Web Search Tool (stubbed, replace with real search API like Tavily or SerpAPI)
def web_search(query: str) -> str:
    return f"Stub: Search results for '{query}'"

tools = [
    Tool(
        name="WebSearch",
        func=web_search,
        description="Useful for searching information on the web"
    ),
    Tool(
        name="GmaillistMessages",
        func=list_messages,
        description="Useful for listing email messages with optional query and labels"
    ),
    Tool(
        name="GmailgetMessage",
        func=get_message,
        description="Useful for getting details of a specific email by its ID"
    ),
    
]