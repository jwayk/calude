import pickle
import os.path

import backoff
from requests_html import HTMLSession
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from schedule import Run


class HTMLInterface:
    def __init__(self, url: str):
        self.url = url
        self.session = HTMLSession()

    def _render_html(self) -> str:
        response = self.session.get(self.url)
        response.html.render()
        return response.html.raw_html

    def get_html(self) -> str:
        return self._render_html()


class CalendarInterface:
    def __init__(self, calendar_id: str):
        self.calendar_id = calendar_id
        self.service = self._authenticate()
        self.cached_events = None

    def _authenticate(self):
        creds = None

        if os.path.exists("_auth/token.pickle"):
            with open("_auth/token.pickle", "rb") as token_file:
                creds = pickle.load(token_file)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "_auth/credentials.json",
                    scopes=["https://www.googleapis.com/auth/calendar"],
                )
                creds = flow.run_local_server(port=0)

            with open("_auth/token.pickle", "wb") as token_file:
                pickle.dump(creds, token_file)

        return build("calendar", "v3", credentials=creds)

    @backoff.on_exception(backoff.expo, HttpError)
    def add_event(self, event: dict):
        self.service.events().insert(calendarId=self.calendar_id, body=event).execute()

    @backoff.on_exception(backoff.expo, HttpError)
    def delete_event(self, event: dict):
        self.service.events().delete(
            calendarId=self.calendar_id, eventId=event["id"]
        ).execute()

    def delete_all_events(self):
        for event in self.get_all_events():
            self.delete_event(event)
        self.cached_events = None

    def _get_events_by_page(self, page_token=None) -> (list, str):
        events_page = (
            self.service.events()
            .list(calendarId=self.calendar_id, pageToken=page_token)
            .execute()
        )
        return events_page["items"], events_page.get("nextPageToken")

    def get_all_events(self):
        if not self.cached_events:
            existing_events, next_page = self._get_events_by_page()
            while next_page:
                next_events, next_page = self._get_events_by_page(next_page)
                existing_events.extend(next_events)
            self.cached_events = existing_events
        return self.cached_events

    def find_outdated_events(self, runs: list[Run]):
        return [
            event
            for event in self.get_all_events()
            if Run.from_gcal_event(event) not in runs
        ]
