from datetime import datetime, timedelta
import re

from bs4 import BeautifulSoup, ResultSet, Tag
from requests_html import HTMLSession


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
        year: str, day: str, start_time: str, estimate: str, timezone_offset: int
    ) -> (str, str):
        day_string = f"{year} {day[0:-2]}"
        start_dt = datetime.strptime(
            f"{day_string} {start_time}", "%Y %A, %B %d %I:%M %p"
        )
        hours, minutes, seconds = [
            int(x) for x in re.match(r"(\d+):(\d+):(\d+)", estimate).groups()
        ]
        end_dt = start_dt + timedelta(hours=hours, minutes=minutes, seconds=seconds)

        start = (
            f"{start_dt.year:04d}-{start_dt.month:02d}-{start_dt.day:02d}T"
            f"{start_dt.hour:02d}:{start_dt.minute:02d}:{start_dt.second:02d}-{timezone_offset:02d}:00"
        )

        end = (
            f"{end_dt.year:04d}-{end_dt.month:02d}-{end_dt.day:02d}T"
            f"{end_dt.hour:02d}:{end_dt.minute:02d}:{end_dt.second:02d}-{timezone_offset:02d}:00"
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
        timezone_offset: int,
    ) -> "Run":
        return cls(
            game,
            f"{runner}\n"
            f"{run_type}\n"
            f"Estimated time: {estimate}\n\n"
            f"Commentary: {host}",
            *cls._generate_datetime_strings(
                year, day, start_time, estimate, timezone_offset
            ),
        )

    def __eq__(self, other):
        return all(
            getattr(self, attr) == getattr(other, attr)
            for attr in ["summary", "description", "start", "end"]
        )


class ScheduleParser:
    schedule_url = "https://gamesdonequick.com/schedule"

    def __init__(self):
        self.session = HTMLSession()
        self.schedule_html = self._render_html()
        self.soup = BeautifulSoup(self.schedule_html, "html.parser")

    def _render_html(self):
        response = self.session.get(self.schedule_url)
        response.html.render()
        return response.html.raw_html

    def _parse_year(self) -> str:
        header = self.soup.find("h1")
        return re.search(
            r".*?(\d{4})(?:\sOnline)?\sSchedule", header.text.strip()
        ).group(1)

    def _get_table_rows(self) -> ResultSet[Tag]:
        run_table = self.soup.find("table", {"id": "runTable"}).find("tbody")
        return run_table.find_all("tr")

    def _parse_timezone_offset(self) -> int:
        tz_banner = self.soup.find("span", {"id": "offset-detected"})
        return int(
            re.search(r"\(detected as UTC-(\d\d):00\)", tz_banner.text.strip()).group(1)
        )

    def parse(self) -> list[Run]:
        year = self._parse_year()
        timezone_offset = self._parse_timezone_offset()
        table_rows = self._get_table_rows()

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
                        timezone_offset,
                    )
                )

        return runs
