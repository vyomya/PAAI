import os
import json
import base64
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def get_service():
    creds = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json',
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def list_messages_tool(json_str):
    """
    Expected input JSON string:
    {
        "query": "from:abc@gmail.com",
        "user_id": "me",
        "label_ids": ["INBOX"],
        "max_results": 25
    }
    """
    try:
        params = json.loads(json_str)
    except:
        return json.dumps({"error": "Invalid JSON input"})

    query = params.get("query", "")
    user_id = params.get("user_id", "me")
    label_ids = params.get("label_ids", [])
    max_results = int(params.get("max_results", 25))
    try:
        if label_ids is None:
            label_ids = []

        service = get_service()

        response = service.users().messages().list(
            userId=user_id,
            labelIds=label_ids,
            q=query,
            maxResults=max_results
        ).execute()

        msgs=response.get('messages', [])
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
        service = get_service()
        msg = service.users().messages().get(
            userId=user_id,
            id=msg_id,
            format='full'
        ).execute()

        headers = msg.get('payload', {}).get('headers', [])
        msg_data = {"id": msg_id, "snippet": msg.get('snippet')}

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

        return json.dumps(msg_data)
    except Exception as e:
        return json.dumps({"error": str(e)})
