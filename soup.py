import re
from time import time
from datetime import datetime, timedelta
import pickle
import os

from bs4 import BeautifulSoup
from requests_html import HTMLSession
import backoff
import pytz
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import settings


class Run:
    def __init__(
        self,
        summary: str,
        description: str,
        start: str,
        end: str,
    ):
        self.summary = summary
        self.description = description
        self.start = start
        self.end = end

    @staticmethod
    def _generate_datetime_strings(
        year: str, day: str, start_time: str, estimate: str
    ) -> (str, str):
        day_string = f"{year} {day[0:-2]}"

        start_dt = datetime.strptime(
            f"{day_string} {start_time}", "%Y %A, %B %d %I:%M %p"
        )
        timezone = pytz.timezone(settings.timezone)
        timezone_offset = 5 - (1 if timezone.localize(start_dt).dst() else 0)

        hours, minutes, seconds = [
            int(x) for x in re.match(r"(\d+):(\d+):(\d+)", estimate).groups()
        ]
        end_dt = start_dt + timedelta(hours=hours, minutes=minutes, seconds=seconds)

        start = (
            f"{start_dt.year:04d}-{start_dt.month:02d}-{start_dt.day:02d}T"
            f"{start_dt.hour:02d}:{start_dt.minute:02d}:{start_dt.second:02d}-0{timezone_offset}:00"
        )

        end = (
            f"{end_dt.year:04d}-{end_dt.month:02d}-{end_dt.day:02d}T"
            f"{end_dt.hour:02d}:{end_dt.minute:02d}:{end_dt.second:02d}-0{timezone_offset}:00"
        )

        return start, end

    def to_gcal_event(self):
        return {
            "summary": self.summary,
            "description": self.description,
            "start": {"dateTime": self.start},
            "end": {"dateTime": self.end},
        }

    @classmethod
    def from_gcal_event(cls, gcal_event: dict) -> "Run":
        return cls(
            gcal_event["summary"],
            gcal_event["description"],
            gcal_event["start"]["dateTime"],
            gcal_event["end"]["dateTime"],
        )

    @classmethod
    def from_parsed_values(
        cls,
        game: str,
        run_type: str,
        runner: str,
        host: str,
        year: str,
        day: str,
        start_time: str,
        estimate: str,
    ) -> "Run":
        return cls(
            game,
            f"{runner}\n"
            f"{run_type}\n"
            f"Estimated time: {estimate}\n\n"
            f"Commentary: {host}",
            *cls._generate_datetime_strings(year, day, start_time, estimate),
        )

    def __eq__(self, other):
        return all(
            getattr(self, attr) == getattr(other, attr)
            for attr in ["summary", "description", "start", "end"]
        )


class Schedule:
    def __init__(self, year: str, runs: list[Run]):
        self.year = year
        self.runs = runs


class ScheduleParser:
    schedule_url = "/".join([settings.gdq_url, settings.schedule_endpoint])

    def __init__(self):
        self.session = HTMLSession()
        self.schedule_html = self._render_html()
        self.soup = BeautifulSoup(self.schedule_html, "html.parser")

    def _render_html(self):
        response = self.session.get(self.schedule_url)
        response.html.render()
        return response.html.raw_html

    def parse(self) -> Schedule:
        header = self.soup.find("h1")
        year = re.search(
            r".*?(\d{4})(?:\sOnline)?\sSchedule", header.text.strip()
        ).group(1)

        run_table = self.soup.find("table", {"id": "runTable"}).find("tbody")
        table_rows = run_table.find_all("tr")

        day = None
        runs = []
        for row in table_rows:
            row_class = row.get("class", [])

            if "day-split" in row_class:
                day = row.find("td").text.strip()
                continue

            if not row_class or (len(row_class) == 1 and "bg-info" in row_class):
                start_time, game, runner, setup = [
                    data.text.strip() for data in row.find_all("td")
                ]
                continue

            if "second-row" in row_class:
                runtime, run_type, host = [
                    data.text.strip() for data in row.find_all("td")
                ]
                runs.append(
                    Run.from_parsed_values(
                        game,
                        run_type,
                        runner,
                        host,
                        year,
                        day,
                        start_time,
                        runtime,
                    )
                )

        return Schedule(year, runs)


class CalendarInterface:
    def __init__(self, calendar_id: str, clear: bool = False):
        self.calendar_id = calendar_id
        self.service = self._authenticate()
        self.cached_events = None
        if clear:
            self.delete_all_events()

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
        self.service.events().insert(
            calendarId=self.calendar_id, body=event
        ).execute()

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

    def find_outdated_events(self, schedule: Schedule):
        return [
            event
            for event in self.get_all_events()
            if Run.from_gcal_event(event) not in schedule.runs
        ]


if __name__ == "__main__":
    print("Parsing GDQ schedule...")
    parser = ScheduleParser()
    schedule = parser.parse()
    print(f"Parsed {len(schedule.runs)} runs")

    print("Initializing calendar interface...")
    calendar = CalendarInterface(settings.calendar_id, settings.clear_calendar)

    existing_events = calendar.get_all_events()
    outdated_events = calendar.find_outdated_events(schedule)
    print(f"Deleting {len(outdated_events)} outdated calendar events...")
    for event in outdated_events:
        calendar.delete_event(event)

    runs_to_add = [
        run
        for run in schedule.runs
        if run not in [Run.from_gcal_event(event) for event in existing_events]
    ]
    print(f"Updating information for {len(runs_to_add)} events...")
    for run in runs_to_add:
        calendar.add_event(run.to_gcal_event())

    print("Done!")
