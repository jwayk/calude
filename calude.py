#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor
import typing as t

import typer
from typing_extensions import Annotated

from lib.interfaces import HTMLInterface, CalendarInterface
from lib.logging import Logger
from lib.schedule import ScheduleParser, Run
from lib.tasks import spin, track
import settings


def initialize_calendar() -> CalendarInterface:
    return CalendarInterface(settings.calendar_id) 


@spin("Initializing calendar & parsing schedule ...")
def initialize() -> t.Tuple[list[Run], CalendarInterface]:
    with ThreadPoolExecutor() as executor:
        calendar_thread = executor.submit(initialize_calendar)
    # schedule parsing must occur in main thread
    schedule_html = HTMLInterface("https://gdq-site.vercel.app/").get_html()
    parser = ScheduleParser(schedule_html)
    return parser.parse(), calendar_thread.result()


@spin("Checking for outdated events ...")
def find_outdated_events(calendar: CalendarInterface, existing_runs: list[Run]) -> list:
    return calendar.find_outdated_events(existing_runs)


def log_format_events(events: t.List[t.Dict]) -> t.List[t.Dict]:
    return [
        {
            "summary": event["summary"],
            "start": event["start"]["dateTime"],
            "end": event["end"]["dateTime"],
        }
        for event in events
    ]


def main(
    parse_only: Annotated[
        bool,
        typer.Option(
            "-p",
            "--parse-only",
            help="Parse the schedule, but do not update any calendars via API.",
        ),
    ] = False,
    clear_calendar: Annotated[
        bool,
        typer.Option(
            "-c",
            "--clear-calendar",
            help="Clear all events from the calendar before updating.",
        ),
    ] = False
):
    log = Logger("calude_updates")
    parsed_runs, calendar = initialize()
    typer.echo(f"Parsed {len(parsed_runs)} runs")

    if parse_only:
        exit(0)

    if clear_calendar:
        all_events = calendar.get_all_events()
        log.debug(f"Cleared Events: {log_format_events(all_events)}")
        track(calendar.delete_event, all_events, "Clearing calendar ...")
        calendar.cached_events = None

    outdated_events = find_outdated_events(calendar, parsed_runs)
    if outdated_events:
        log.debug(f"Outdated Events: {log_format_events(outdated_events)}")
        track(calendar.delete_event, outdated_events, "Deleting outdated events ...")
    else:
        typer.echo("No outdated events.")

    existing_events = calendar.get_all_events()
    events_to_add = [
        run.to_gcal_event()
        for run in parsed_runs
        if run not in [Run.from_gcal_event(event) for event in existing_events]
    ]
    if events_to_add:
        log.debug(f"New Events: {log_format_events(events_to_add)}")
        track(calendar.add_event, events_to_add, "Adding events to calendar ...")
    else:
        typer.echo("No runs to add; calendar is up-to-date.")

    typer.echo("Done!")


if __name__ == "__main__":
    typer.run(main)
