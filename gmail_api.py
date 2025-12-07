import os
import json
import base64
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


# Gmail scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


# ---------------------------------------------------------
# 1. AUTHENTICATION / SERVICE INITIALIZATION
# ---------------------------------------------------------
def get_service():
    creds = None

    # If token exists, load it
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # If no valid token → login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json',
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


# ---------------------------------------------------------
# 2. RAW GMAIL FUNCTIONS
# ---------------------------------------------------------
def list_messages(query='', user_id='me', label_ids=None):
    """
    Returns list of message metadata (IDs only).
    """
    if label_ids is None:
        label_ids = []

    service = get_service()

    response = service.users().messages().list(
        userId=user_id,
        labelIds=label_ids,
        q=query
    ).execute()

    return response.get('messages', [])


def get_message(msg_id, user_id='me'):
    """
    Returns detailed email content (subject, from, date, body, etc.)
    """
    service = get_service()

    msg = service.users().messages().get(
        userId=user_id,
        id=msg_id,
        format='full'
    ).execute()

    headers = msg.get('payload', {}).get('headers', [])
    msg_data = {"id": msg_id, "snippet": msg.get('snippet')}

    # Extract useful headers
    for h in headers:
        name = h['name'].lower()
        value = h['value']

        if name == 'from':
            msg_data['from'] = value
        elif name == 'to':
            msg_data['to'] = value
        elif name == 'subject':
            msg_data['subject'] = value
        elif name == 'date':
            try:
                msg_data['date'] = str(parsedate_to_datetime(value))
            except:
                msg_data['date'] = value

    # Extract simple text body
    body = None
    payload = msg.get('payload', {})

    try:
        parts = payload.get('parts', [])
        for part in parts:
            if part.get('mimeType') == 'text/plain':
                data = part.get('body', {}).get('data', '')
                body = base64.urlsafe_b64decode(data).decode('utf-8')
    except Exception:
        pass

    msg_data['body'] = body

    return msg_data


# ---------------------------------------------------------
# 3. LLM-FRIENDLY TOOL WRAPPERS (Single-string JSON input)
# ---------------------------------------------------------
def list_messages_tool(json_str):
    """
    Expected input JSON string:
    {
        "query": "from:abc@gmail.com",
        "user_id": "me",
        "label_ids": ["INBOX"]
    }
    """
    try:
        params = json.loads(json_str)
    except:
        return json.dumps({"error": "Invalid JSON input"})

    query = params.get("query", "")
    user_id = params.get("user_id", "me")
    label_ids = params.get("label_ids", [])

    try:
        msgs = list_messages(query=query, user_id=user_id, label_ids=label_ids)
        return json.dumps(msgs)
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_message_tool(json_str):
    """
    Expected input JSON string:
    {
        "msg_id": "...",
        "user_id": "me"
    }
    """
    try:
        params = json.loads(json_str)
    except:
        return json.dumps({"error": "Invalid JSON input"})

    if "msg_id" not in params:
        return json.dumps({"error": "msg_id is required"})

    msg_id = params["msg_id"]
    user_id = params.get("user_id", "me")

    try:
        message = get_message(msg_id=msg_id, user_id=user_id)
        return json.dumps(message)
    except Exception as e:
        return json.dumps({"error": str(e)})
