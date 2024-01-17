from datetime import datetime, timedelta
import re
from itertools import chain

from bs4 import BeautifulSoup, ResultSet, Tag


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
            f"{year} {day[0:-2]} {start_time}", "%Y %a, %b %d %I:%M %p"
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
        run_category: str,
        platform: str,
        runners: list[str],
        host: str,
        couch: list[str],
        year: str,
        day: str,
        start_time: str,
        estimate: str,
        timezone_offset: int,
    ) -> "Run":
        return cls(
            game,
            f"{', '.join(runners)}\n"
            f"{run_category} {platform if platform else ''}\n"
            f"Estimated time: {estimate}\n\n"
            f"Host: {host}" + ("\n" + f"Couch: {', '.join(couch)}" if couch else ""),
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
        title = self.soup.find("title")
        return re.search(
            r".*?(\d{4})(?:\sOnline)?\sSchedule", title.text.strip()
        ).group(1)

    def _parse_timezone_offset(self) -> int:
        return -5  # new schedule is currently hard-coded to America/New_York

    def _find_event_containers(self) -> ResultSet[Tag]:
        schedule_container = self.soup.find("div", {"id": "radix-:r0:-content-All"})
        events_container = schedule_container.find_all("div", recursive=False)[
            1
        ]  # first div in main container is controls, skip it
        return events_container.find_all("div", recursive=False)

    def _parse_single_run_from_div(self, div: Tag) -> dict:
        event_subdivs = iter(div.find_all("div", recursive=False))
        title_div = next(event_subdivs)
        description_div = next(event_subdivs)
        if not title_div.text:
            return {}  # no listed title or start time

        event_title = title_div.find("span", {"class": "font-bold"})
        event_start = title_div.find("div", {"class": "font-light"}, recursive=False)
        if not (event_title and event_start):
            return {}  # pre-show-like event without a title

        title, start_time = (
            info.find(string=True) for info in [event_title, event_start]
        )

        description_subdivs = iter(description_div.find_all("div", recursive=False))
        meta_div = next(description_subdivs)
        cast_div = next(description_subdivs)
        incentive_div = next(description_subdivs, None)

        event_type = meta_div.find("label", recursive=False).text
        metadata = meta_div.find("div", {"class": "session-title"})
        metadata_spans = (
            metadata.find("div", {"class": "items-center"})
            .find("span")
            .find_all("span")
        )
        if len(metadata_spans) == 2:
            run_category = metadata_spans[0].text
            platform = None
            estimate_text = metadata_spans[1].text
        else:
            run_category, platform, estimate_text = [
                span.text for span in metadata_spans
            ]

        estimate = re.match(r"\((?:Est: )?(.*)\)", estimate_text).group(1)

        runner_constraint = {"class": "ring-[color:var(--accent-purple)]"}
        runners = [
            runner_element.text
            for runner_element in chain(
                *[cast_div.find_all(tag, runner_constraint) for tag in ["a", "span"]]
            )
        ]
        host = cast_div.find("span", {"class": "ring-[color:var(--gdq-blue)]"}).text
        couch_members = [
            element.text
            for element in cast_div.find_all(
                "span", {"class": "ring-[color:var(--accent-goldenrod)]"}
            )
        ]

        return {
            "game": title,
            "run_category": run_category,
            "platform": platform,
            "runners": runners,
            "host": host,
            "couch": couch_members,
            "start_time": start_time,
            "estimate": estimate,
        }

    def parse(self) -> list[Run]:
        year = self._parse_year()
        timezone_offset = self._parse_timezone_offset()
        all_schedule_divs = self._find_event_containers()

        day = None
        runs = []
        for div in all_schedule_divs:
            child_span = div.find("span", {"class": "flex"}, recursive=False)
            if child_span and (
                span_text := child_span.find(string=True, recursive=False)
            ):
                day = span_text.strip()
                continue

            parsed_event_info = self._parse_single_run_from_div(div)
            if not parsed_event_info:
                continue

            runs.append(
                Run.from_parsed_values(
                    year=year,
                    day=day,
                    timezone_offset=timezone_offset,
                    **parsed_event_info,
                )
            )

        return runs
