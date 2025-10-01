
import os.path
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.utils import parsedate_to_datetime

# If modifying scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_service():
    creds = None
    # Load existing credentials
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If no valid credentials, let user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save credentials for future use
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)
def list_messages(service, query ='', user_id='me', label_ids=[]):
    """List all Messages Ids of the user's mailbox matching query.
    Arguments:
    service -- Authorized Gmail API service instance.
    query -- String used to filter messages returned.
             Eg.- 'from:user@some_domain.com is:unread' for Messages from a particular sender. 
             Eg.- 'after:2025/09/16 before:2025/09/18' for Messages in a particular date range.
    user_id -- User's email address. The special value "me"
               can be used to indicate the authenticated user.
    label_ids -- Only return Messages with these labelIds applied. eg. ['INBOX']

    Response:
    List of Messages that match the criteria of the query. Note that the returned list contains Message IDs and threadID, not the Messages themselves.
    """
    query = f'{query}'
    results = service.users().messages().list(userId=user_id, labelIds=label_ids, q=query).execute()
    messages = results.get('messages', [])
    return messages


def get_message(service, msg_id, user_id='me'):
    """Get a Message and extract useful fields
    Arguments:
    service -- Authorized Gmail API service instance.
    msg_id -- The ID of the Message required.
    user_id -- User's email address. The special value "me"
                can be used to indicate the authenticated user.
    Response:
    A dictionary containing id, snippet, from, to, subject, date, body of the email.
    """
    message = service.users().messages().get(userId=user_id, id=msg_id, format='full').execute()

    headers = message['payload']['headers']
    msg_data = {"id": msg_id, "snippet": message.get('snippet')}

    # Extract common headers
    for h in headers:
        name = h['name'].lower()
        if name == 'from':
            msg_data['from'] = h['value']
        elif name == 'to':
            msg_data['to'] = h['value']
        elif name == 'subject':
            msg_data['subject'] = h['value']
        elif name == 'date':
            # Convert to datetime
            msg_data['date'] = parsedate_to_datetime(h['value'])

    # Extract body (simple case: text/plain)
    body = None
    try:
        parts = message['payload']['parts']
        for part in parts:
            if part['mimeType'] == 'text/plain':
                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
    except:
        pass
    msg_data['body'] = body

    return msg_data


if __name__ == '__main__':
    service = get_service()

    # Get INBOX (incoming mails)
    inbox_msgs = list_messages(service, label_ids=['INBOX'])
    print("Inbox emails:")
    print(inbox_msgs[0])
    print(len(inbox_msgs))
    
    for m in inbox_msgs[:5]:  # limit to first 5
        print(get_message(service, m['id']))

    # Get SENT (outgoing mails)
    sent_msgs = list_messages(service, label_ids=['SENT'])
    print("\nSent emails:")
    for m in sent_msgs[:5]:
        print(get_message(service, m['id']))
