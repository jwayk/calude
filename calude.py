#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor

from rich.progress import track, Progress, SpinnerColumn, TextColumn
import typer
from typing_extensions import Annotated

from schedule import ScheduleParser, Run
from interfaces import HTMLInterface, CalendarInterface
import settings


def get_spinner():
    return Progress(
        TextColumn("{task.description}"), SpinnerColumn("line", finished_text="done")
    )


def parse_schedule():
    schedule_html = HTMLInterface("https://gamesdonequick.com/schedule").get_html()
    parser = ScheduleParser(schedule_html)
    parsed_runs = parser.parse()
    return parsed_runs


def initialize_calendar():
    calendar = CalendarInterface(settings.calendar_id)
    return calendar


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
    with get_spinner() as spinner:
        task = spinner.add_task("Initializing calendar & parsing schedule ...", total=1)
        with ThreadPoolExecutor() as executor:
            calendar_thread = executor.submit(initialize_calendar)
            parsed_runs = (
                parse_schedule()
            )  # schedule parsing must be done in main thread
            calendar = calendar_thread.result()
        spinner.update(task, completed=1)
    typer.echo(f"Parsed {len(parsed_runs)} runs")

    if clear_calendar:
        for event in track(calendar.get_all_events(), "Clearing calendar..."):
            calendar.delete_event(event)
        calendar.cached_events = None

    with get_spinner() as spinner:
        task = spinner.add_task("Checking for outdated events ...", total=1)
        outdated_events = calendar.find_outdated_events(parsed_runs)
        spinner.update(task, completed=1)

    if outdated_events:
        for event in track(outdated_events, "Deleting outdated events..."):
            calendar.delete_event(event)
    else:
        typer.echo("No outdated events.")

    existing_events = calendar.get_all_events()
    runs_to_add = [
        run
        for run in parsed_runs
        if run not in [Run.from_gcal_event(event) for event in existing_events]
    ]
    if runs_to_add:
        for run in track(runs_to_add, "Adding events to calendar..."):
            calendar.add_event(run.to_gcal_event())
    else:
        typer.echo("No runs to add - calendar is up-to-date.")

    typer.echo("Done!")


if __name__ == "__main__":
    typer.run(main)
