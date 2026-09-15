import os
from datetime import datetime, timedelta

from google.auth import default as google_auth_default
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import json


SCOPES = ["https://www.googleapis.com/auth/calendar"]


def create_calendar_service(credentials_json: str = None, scopes=None):
    """Create a Google Calendar API service client.

    If credentials_json is provided, a service account file is used.
    Otherwise, application default credentials are used.
    """
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

    return build('calendar', 'v3', credentials=creds)


def list_calendars(service):
    """List calendars available to the authenticated account."""
    try:
        page_token = None
        calendars = []
        while True:
            calendar_list = service.calendarList().list(pageToken=page_token).execute()
            calendars.extend(calendar_list.get("items", []))
            page_token = calendar_list.get("nextPageToken")
            if not page_token:
                break
        return calendars
    except HttpError as error:
        raise RuntimeError(f"Failed to list calendars: {error}") from error


def list_events(json_str):
    """Retrieve events from a calendar."""
    service = create_calendar_service()
    
    try:
        params = json.loads(json_str)
    except:
        return json.dumps({"error": "Invalid JSON input"})
    calendar_id="primary"
    time_min = params.get("time_min", "")
    time_max = params.get("time_max", "me")
    max_results = int(params.get("max_results", 10))
    try:
        if time_min is None:
            time_min = datetime.utcnow().isoformat() + "Z"
        if time_max is None:
            time_max = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=max_results,
            )
            .execute()
        )
        return json.dumps(events_result.get("items", []))
    except HttpError as error:
        raise RuntimeError(f"Failed to get events: {error}") from error


def create_event(service, calendar_id="primary", event=None):
    """Create an event on the specified calendar."""
    if event is None:
        raise ValueError("Event payload must be provided")

    try:
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
        return created_event
    except HttpError as error:
        raise RuntimeError(f"Failed to create event: {error}") from error


# if __name__ == "__main__":
#     credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
#     service = create_calendar_service(credentials_path)
#     calendars = list_calendars(service)
#     print(list_events(service))
#     print("Calendars:")
#     for cal in calendars:
#         print(f"- {cal.get('summary')} ({cal.get('id')})")
