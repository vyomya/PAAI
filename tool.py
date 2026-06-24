from langchain_core.tools import Tool
import json
from gmail_api import list_messages_tool, get_message_tool
from calendar_api import list_events
from generic_tools import get_time
from db import search_messages, get_recent_messages

def web_search(query: str) -> str:
    return f"Stub: Search results for '{query}'"

def GetRecentMessages(input: str) -> str:
    """
    Returns the most recent conversation messages in chronological order.
    Input JSON: {"limit": 10}
    Use this when user references something from the last response 
    ("point 8", "that email", "what you just said").
    """
    try:
        args = json.loads(input)
        limit = args.get("limit", 10)
    except:
        limit = 10

    messages = get_recent_messages(limit=limit)
    if not messages:
        return "No conversation history found."
    return json.dumps(messages, indent=2)


def SearchMessages(input: str) -> str:
    """
    Semantically searches conversation history for relevant past messages.
    Input JSON: {"query": "interview discussion", "limit": 5}
    Use this when user references a specific topic from a past session
    ("our discussion about interviews", "what we said about Bosch last week").
    """
    try:
        args = json.loads(input)
        query = args.get("query", "")
        limit = args.get("limit", 5)
    except:
        return "Invalid input."

    messages = search_messages(query=query, limit=limit)
    if not messages:
        return "No relevant messages found."
    return json.dumps(messages, indent=2)
tools = [
    Tool(
        name="GetTime",
        func = get_time,
        description="""Gets the Current Date and Time, in order to get more context of User prompt
        Input is empty ,always gives current time and date:
        { }
        """
    ),
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
        name="FetchCalendarEvents",
        func=list_events,
        description="""Fetches Calender Events from Google Events. 
        Input must be a JSON string with optional fields:
        {"time_min": "the start of time frame in which you want the calendar events", "time_max": "the start of time frame in which you want the calendar events", "max_results": 10}
        Query examples:
        - "time_min": "time+Date" - events after this date
        - "time_max": "time+Date+7" - events till this date
        - "max_results": 10 - choose number of emails you want to fetch
        Returns a JSON string with a list of event objects containing event IDs and event information.
        Example input: '{"time_min": "2026-05-23T18:20:46.600724Z","time_max":"2026-05-30T18:21:20.637654Z", "max_results": 10}'
        """
    )
    ,Tool(
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
    Tool(
        name="SearchMessages",
        func=SearchMessages,
        description="""Semantically searches conversation history for relevant past messages.
        Input must be a JSON string: {"query": "search terms", "limit": 5}
        Use this when user references a specific topic from a past session  ("our discussion about interviews", "what we said about Bosch last week").
        Returns a JSON string with a list of relevant messages.
        Example input: '{"query": "interview discussion", "limit": 5}'
        """
    ),
    Tool(
        name="GetRecentMessages",
        func=GetRecentMessages,
        description="""Returns the most recent conversation messages in chronological order.
        Input must be a JSON string: {"limit": 10}
        Use this when user references something from the last response ("point 8", "that email", "what you just said").
        Returns a JSON string with a list of recent messages.
        Example input: '{"limit": 10}'
        """
    )
]
