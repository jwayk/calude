#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor
import typing as t
import re
import json

import typer
from typing_extensions import Annotated

from lib.interfaces import HTMLInterface, CalendarInterface
from lib.logging import Logger
from lib.schedule import ScheduleParser, Run
from lib.tasks import spin, track


def initialize_calendar(calendar_id: str) -> CalendarInterface:
    return CalendarInterface(calendar_id) if calendar_id else None


@spin("Initializing calendar & parsing schedule ...")
def initialize(calendar_id: str) -> t.Tuple[list[Run], CalendarInterface]:
    with ThreadPoolExecutor() as executor:
        calendar_thread = executor.submit(initialize_calendar, calendar_id)
    # schedule parsing must occur in main thread
    site_interface = HTMLInterface("https://gdq-site.vercel.app/")
    schedule_html = site_interface.get_html()
    site_interface.driver.quit()
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


def validate_gcal_id(calendar_id: str) -> t.Union[str, None]:
    if calendar_id is None:
        return calendar_id

    try:
        cal_id, domain = calendar_id.split("@")
    except ValueError:
        raise typer.BadParameter(
            "Calendar ID must be supplied in the format '<ID64>@<DOMAIN>'"
        )

    group_domain = "group.calendar.google.com"
    if domain != group_domain:
        raise typer.BadParameter(
            f"Calendar domain must point to a group calendar ({group_domain})"
        )

    if not re.match(r"[\w\d]{64}", cal_id):
        raise typer.BadParameter("Calendar ID must be 64 characters")

    return calendar_id


def main(
    google_calendar_id: Annotated[
        str,
        typer.Option(
            "-g",
            "--gcal-id",
            callback=validate_gcal_id,
            help="ID of the Google calendar to update.",
        ),
    ] = None,
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
            help="Clear all events from third-party calendar services before updating.",
        ),
    ] = False,
):
    if not parse_only and not google_calendar_id:
        raise typer.BadParameter(
            "A calendar ID must be specified with '-g' for third-party calendar functionality. "
            "Try running with '--parse-only' to bypass this."
        )
    log = Logger("calude_updates")
    parsed_runs, calendar = initialize(google_calendar_id)
    typer.echo(f"Parsed {len(parsed_runs)} runs")

    if parse_only:
        with open("logs/events_from_last_run.json", "w+") as cache_file:
            cache_file.write(json.dumps([run.to_gcal_event() for run in parsed_runs], indent=4))
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
