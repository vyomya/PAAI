from langchain.agents import Tool
from gmail_api import list_messages_tool, get_message_tool

# --- Define Tools ---

# 1. Web Search Tool (stubbed, replace with real search API like Tavily or SerpAPI)
def web_search(query: str) -> str:
    return f"Stub: Search results for '{query}'"

tools = [
    Tool(
        name="WebSearch",
        func=web_search,
        description="Useful for searching information on the web. Input should be a search query string."
    ),
    Tool(
        name="FetchEmails",
        func=list_messages_tool,
        description="""Fetches email messages from Gmail. 
        Input must be a JSON string with optional fields:
        {"query": "search terms like 'after:2024/11/29'", "user_id": "me", "label_ids": ["INBOX"]}
        
        Query examples:
        - "after:2024/11/29" - emails after this date
        - "from:user@example.com" - emails from specific sender
        - "subject:meeting" - emails with 'meeting' in subject
        
        Returns a JSON string with a list of message objects containing message IDs.
        You must then use GetEmailDetails to get the full content of each email.
        
        Example input: '{"query": "after:2024/11/29", "label_ids": ["INBOX"]}'
        """
    ),
    Tool(
        name="GetEmailDetails",
        func=get_message_tool,
        description="""Gets full details of a specific email by its message ID.
        Input must be a JSON string: {"msg_id": "message_id_here", "user_id": "me"}
        
        Returns email details including:
        - from: sender email
        - to: recipient email
        - subject: email subject
        - date: when email was sent
        - body: email body text
        - snippet: preview text
        
        Example input: '{"msg_id": "18a1b2c3d4e5f6g7"}'
        """
    ),
]