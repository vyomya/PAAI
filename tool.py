from langchain_core.tools import Tool
from gmail_api import list_messages_tool, get_message_tool

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
        {"query": "search terms like 'after:date'", "user_id": "me", "label_ids": ["INBOX"], "max_results": 25}
        Query examples:
        - "after:date" - emails after this date
        - "from:user@example.com" - emails from specific sender
        - "subject:meeting" - emails with 'meeting' in subject
        - "max_results": 25 - choose number of emails you want to fetch
        Returns a JSON string with a list of message objects containing message IDs.
        You must then use GetEmailDetails to get the full content of each email.
        Example input: '{"query": "after:2024-01-01", "label_ids": ["INBOX"], "max_results": 10}'
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