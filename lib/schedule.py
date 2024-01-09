from datetime import datetime, timedelta
import re

from bs4 import BeautifulSoup, ResultSet, Tag
from requests_html import HTMLSession


class Run:
    _essential_attrs = ["summary", "description", "start", "end"]

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
        year: str, day: str, start_time: str, estimate_string: str, timezone_offset: int
    ) -> (str, str):
        def format_dt(dt: datetime) -> str:
            dt_utc = dt - timedelta(hours=timezone_offset)
            return dt_utc.strftime(f"%Y-%m-%dT%H:%M:%SZ")

        estimate = datetime.strptime(estimate_string, "%H:%M:%S")
        start_dt = datetime.strptime(
            f"{year} {day[0:-2]} {start_time}", "%Y %A, %B %d %I:%M %p"
        )
        end_dt = start_dt + timedelta(
            hours=estimate.hour, minutes=estimate.minute, seconds=estimate.second
        )

        return format_dt(start_dt), format_dt(end_dt)

    def to_gcal_event(self):
        return {
            "summary": self.summary,
            "description": self.description,
            "start": {"dateTime": self.start, "timeZone": "Etc/UTC"},
            "end": {"dateTime": self.end, "timeZone": "Etc/UTC"},
        }

    @classmethod
    def from_gcal_event(cls, gcal_event: dict) -> "Run":
        def convert_to_utc(date: dict):
            dt_format = "%Y-%m-%dT%H:%M:%S"
            date_string = date["dateTime"]
            dt = datetime.strptime(date["dateTime"][:19], dt_format)
            if len(date_string) > 20:
                offset_polarity = int(date["dateTime"][19] + "1")
                dt = dt - (
                    offset_polarity
                    * timedelta(
                        hours=int(date["dateTime"][-5:-3]),
                        minutes=int(date["dateTime"][-2:]),
                    )
                )
            return dt.strftime(dt_format) + "Z"

        return cls(
            gcal_event["summary"],
            gcal_event["description"],
            convert_to_utc(gcal_event["start"]),
            convert_to_utc(gcal_event["end"]),
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

    def __repr__(self):
        repr_string = ", ".join(
            [repr(getattr(self, attr)) for attr in self._essential_attrs]
        )
        return f"Run({repr_string})"

    def __eq__(self, other):
        return all(
            getattr(self, attr) == getattr(other, attr)
            for attr in self._essential_attrs
        )


class ScheduleParser:
    def __init__(self, schedule_html: str):
        self.soup = BeautifulSoup(schedule_html, "html.parser")

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
        regex_match = re.search(
            r"\(detected as UTC([+-]\d\d):00\)", tz_banner.text.strip()
        )
        if not regex_match:
            return 0  # displayed time is utc
        return int(regex_match.group(1))

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
                        runtime if runtime else setup,
                        timezone_offset,
                    )
                )

        return runs
