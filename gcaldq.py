from concurrent.futures import ThreadPoolExecutor

from schedule_parser import ScheduleParser, Run
from google_interface import CalendarInterface
import settings


def parse_schedule():
    print("Parsing GDQ schedule...")
    parser = ScheduleParser()
    parsed_runs = parser.parse()
    print(f"Parsed {len(parsed_runs)} runs")
    return parsed_runs

def initialize_calendar():
    print("Initializing calendar interface...")
    return CalendarInterface(settings.calendar_id, settings.clear_calendar)


if __name__ == "__main__":

    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(lambda function: function(), parse_schedule, initialize_calendar)
        parsed_runs, calendar = future.result()

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
