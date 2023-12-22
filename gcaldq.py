#!/usr/bin/env python3

from concurrent.futures import ThreadPoolExecutor

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
    return CalendarInterface(settings.calendar_id, settings.clear_calendar)


if __name__ == "__main__":
    with ThreadPoolExecutor() as executor:
        calendar_thread = executor.submit(initialize_calendar)
        parsed_runs = parse_schedule()  # schedule parsing must be done in main thread
        calendar = calendar_thread.result()

    existing_events = calendar.get_all_events()
    outdated_events = calendar.find_outdated_events(parsed_runs)
    print(f"Deleting {len(outdated_events)} outdated calendar events...")
    for event in outdated_events:
        calendar.delete_event(event)

    runs_to_add = [
        run
        for run in parsed_runs
        if run not in [Run.from_gcal_event(event) for event in existing_events]
    ]
    print(f"Updating information for {len(runs_to_add)} events...")
    for run in runs_to_add:
        calendar.add_event(run.to_gcal_event())

    print("Done!")
