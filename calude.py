#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor
import typing as t

import typer
from typing_extensions import Annotated

from lib.schedule import ScheduleParser, Run
from lib.interfaces import HTMLInterface, CalendarInterface
from lib.tasks import spin, track
import settings


def initialize_calendar() -> CalendarInterface:
    calendar = CalendarInterface(settings.calendar_id)
    return calendar


@spin("Initializing calendar & parsing schedule ...")
def initialize() -> t.Tuple[list[Run], CalendarInterface]:
    with ThreadPoolExecutor() as executor:
        calendar_thread = executor.submit(initialize_calendar)
    # schedule parsing must occur in main thread
    schedule_html = HTMLInterface("https://gamesdonequick.com/schedule").get_html()
    parser = ScheduleParser(schedule_html)
    return parser.parse(), calendar_thread.result()


@spin("Checking for outdated events ...")
def find_outdated_events(calendar: CalendarInterface, existing_runs: list[Run]) -> list:
    return calendar.find_outdated_events(existing_runs)


def main(
    clear_calendar: Annotated[
        bool,
        typer.Option(
            "-c",
            "--clear-calendar",
            help="Clear all events from the calendar before updating.",
        ),
    ] = False
):
    parsed_runs, calendar = initialize()
    typer.echo(f"Parsed {len(parsed_runs)} runs")

    if clear_calendar:
        track(calendar.delete_event, calendar.get_all_events(), "Clearing calendar ...")
        calendar.cached_events = None

    outdated_events = find_outdated_events(calendar, parsed_runs)
    if outdated_events:
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
        track(calendar.add_event, events_to_add, "Adding events to calendar ...")
    else:
        typer.echo("No runs to add; calendar is up-to-date.")

    typer.echo("Done!")


if __name__ == "__main__":
    typer.run(main)
