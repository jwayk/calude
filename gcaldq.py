#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor

from rich.progress import track
import typer
from typing_extensions import Annotated

from schedule import ScheduleParser, Run
from interfaces import HTMLInterface, CalendarInterface
import settings


def parse_schedule():
    print("Parsing GDQ schedule...")
    schedule_html = HTMLInterface("https://gamesdonequick.com/schedule").get_html()
    parser = ScheduleParser(schedule_html)
    parsed_runs = parser.parse()
    print(f"Parsed {len(parsed_runs)} runs")
    return parsed_runs


def initialize_calendar():
    print("Initializing calendar interface...")
    return CalendarInterface(settings.calendar_id)


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
    with ThreadPoolExecutor() as executor:
        calendar_thread = executor.submit(initialize_calendar)
        parsed_runs = parse_schedule()  # schedule parsing must be done in main thread
        calendar = calendar_thread.result()

    existing_events = calendar.get_all_events()

    if clear_calendar:
        for event in track(calendar.get_all_events(), "Clearing calendar..."):
            calendar.delete_event(event)
        calendar.cached_events = None

    outdated_events = calendar.find_outdated_events(parsed_runs)
    if outdated_events:
        for event in track(outdated_events, "Deleting outdated events..."):
            calendar.delete_event(event)

    runs_to_add = [
        run
        for run in parsed_runs
        if run not in [Run.from_gcal_event(event) for event in existing_events]
    ]
    if runs_to_add:
        for run in track(runs_to_add, "Adding events to calendar..."):
            calendar.add_event(run.to_gcal_event())

    typer.echo("Done!")


if __name__ == "__main__":
    typer.run(main)
