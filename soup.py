import re
import json
from time import time
from datetime import datetime, timedelta
import pickle
import os

import urllib3
from bs4 import BeautifulSoup
import backoff
import pytz
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import settings


class ScheduleParser:
    schedule_url = "/".join([settings.gdq_url, settings.schedule_endpoint])

    def __init__(self):
        self.schedule_html = None


class CalendarInterface:
    def __init__(self, calendar_id: str, clear_before_updating: bool = False):
        self.calendar_id = calendar_id
        self.clear = clear_before_updating
        self.service = self._authenticate()

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
    def _add_event(self, event: dict):
        self.service.events().insert(
            calendarId=self.calendar_id, eventId=event["id"]
        ).execute()

    @backoff.on_exception(backoff.expo, HttpError)
    def _delete_event(self, event: dict):
        self.service.events().delete(
            calendarId=self.calendar_id, eventId=event["id"]
        ).execute()

    def _get_events_page(self, page_token=None) -> tuple[list, str]:
        events_page = self.service.events().list(calendarId=self.calendar_id, pageToken=page_token).execute()
        return events_page["items"], events_page.get("nextPageToken")

    def _retrieve_events(self):
        existing_events, next_page = self._get_events_page()
        while next_page:
            next_events, next_page = self._get_events_page(next_page)
            print(type(next_page))
            existing_events.extend(next_events)
        return existing_events


if __name__ == "__main__":
    http = urllib3.PoolManager()

    response = http.request("GET", "https://gamesdonequick.com/schedule")
    soup = BeautifulSoup(response.data)

    header = soup.find("h1")
    year = re.search(r".*?(\d{4})(?:\sOnline)?\sSchedule", header.text).group(1)

    run_table = soup.find("table", {"id": "runTable"}).find("tbody")
    table_rows = run_table.find_all("tr")

    day = None
    events = []
    for row in table_rows:
        row_class = row.get("class", [])

        if "day-split" in row_class:
            day = row.find("td").text
            # print(day)
            continue

        if not row_class or (len(row_class) == 1 and "bg-info" in row_class):
            time, game, runner, setup = [data.text for data in row.find_all("td")]
            continue

        if "second-row" in row_class:
            runtime, run_type, commentary = [data.text for data in row.find_all("td")]
            events.append(
                {
                    "day": day,
                    "start": time,
                    "game": game,
                    "runner": runner,
                    "runtime": runtime,
                    "run_type": run_type,
                    "commentary": commentary,
                }
            )

    print(len(events))

    # print(json.dumps(events, indent=4))
    # print(soup.prettify())
    # print(header.text)
    # print(run_table)
