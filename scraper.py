from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import re
import sys
import pytz
import json
# import logging
from time import (
    time,
    sleep,
)
from datetime import (
    datetime,
    timedelta,
)
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
import backoff

import settings


# logging.basicConfig(
#     stream=sys.stdout,
#     level=logging.DEBUG,
#     format="[%(asctime)s] %(message)s",
#     datefmt="%d-%b-%y %H:%M:%S"
# )


def create_datetimes(year, event):

    daystr = f"{year} {event['day'][0:-2]}"

    dt_start = datetime.strptime(f"{daystr} {event['start']}", "%Y %A, %B %d %I:%M %p")
    est = pytz.timezone("US/Eastern")
    timezone_offset = 5 - (1 if est.localize(dt_start).dst() else 0)

    hours, minutes, seconds = [int(x) for x in re.match(r"(\d+):(\d+):(\d+)", event["runtime"]).groups()]
    dt_end = dt_start + timedelta(hours=hours, minutes=minutes, seconds=seconds)

    start = f"{dt_start.year:04d}-{dt_start.month:02d}-{dt_start.day:02d}T" \
            f"{dt_start.hour:02d}:{dt_start.minute:02d}:{dt_start.second:02d}-0{timezone_offset}:00"

    end = f"{dt_end.year:04d}-{dt_end.month:02d}-{dt_end.day:02d}T" \
          f"{dt_end.hour:02d}:{dt_end.minute:02d}:{dt_end.second:02d}-0{timezone_offset}:00"

    return start, end


def scrape_schedule():

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.binary_location = settings.selenium_binaries["browser"]

    driver = webdriver.Chrome(options, Service(settings.selenium_binaries["driver"]))
    driver.get("https://gamesdonequick.com/schedule")

    header = driver.find_element(By.TAG_NAME, "h1")
    year = re.search(r".*?(\d{4})(?:\sOnline)?\sSchedule", header.text).group(1)

    run_table = driver.find_element(By.ID, "runTable")
    table_rows = run_table.find_elements(By.TAG_NAME, "tr")

    day = None
    events = []
    for row in table_rows:

        row_class = row.get_attribute("class")

        if "day-split" in row_class:
            day = row.text
            continue

        if not row_class or row_class == "bg-info":

            time, game, runner, setup = [x.text for x in row.find_elements(By.TAG_NAME, "td")]
            continue

        if "second-row" in row_class:

            runtime, runtype, commentary = [x.text for x in row.find_elements(By.TAG_NAME, "td")]
            events.append({
                "day": day,
                "start": time,
                "game": game,
                "runner": runner,
                "runtime": runtime,
                "runtype": runtype,
                "commentary": commentary,
            })

    driver.quit()
    return year, events


def calendar_auth():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', settings.gcal["scopes"])
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('calendar', 'v3', credentials=creds)


last_string = ""


def progress(prog, total):

    global last_string

    sys.stdout.write("\b" * len(last_string))
    last_string = f"{prog}/{total} queries sent."
    sys.stdout.write(last_string)
    sys.stdout.flush()


def simplify_gcal(event: dict):

    # there is sometimes a "timeZone" key in event start/end
    # this is the simplest way to circumvent so events can be compared
    return {
        "summary": event["summary"],
        "description": event["description"],
        "start": {
            "dateTime": event["start"]["dateTime"]
        },
        "end": {
            "dateTime": event["end"]["dateTime"]
        }
    }


def is_outdated(event: dict, current_list: list):

    return True if simplify_gcal(event) not in current_list else False


@backoff.on_exception(backoff.expo, HttpError)
def add_event(svc, event: dict):

    svc.events().insert(calendarId=settings.gcal["id"], body=event).execute()


@backoff.on_exception(backoff.expo, HttpError)
def delete_event(svc, event: dict):

    svc.events().delete(calendarId=settings.gcal["id"], eventId=event["id"]).execute()


if __name__ == "__main__":

    exc_start = time()

    print("Initializing Calendar API...")
    service = calendar_auth()

    print("Retrieving current calendar state...")
    page_token = None
    existing_events = []

    while True:

        event_page = service.events().list(calendarId=settings.gcal["id"], pageToken=page_token).execute()

        [existing_events.append(event) for event in event_page["items"]]

        page_token = event_page.get("nextPageToken")
        if not page_token:
            break

    print()
    print(
        "Scraping GDQ schedule...\n"
        "(This will take some time)"
    )
    event_year, runs = scrape_schedule()

    print("Building queries...")
    gdq_events = []
    for run in runs:

        start, end = create_datetimes(event_year, run)
        event = {
            "summary": run["game"],
            "description": f"{run['runner']}\n"
                           f"{run['runtype']}\n"
                           f"Estimated time: {run['runtime']}\n\n"
                           f"Commentary: {run['commentary']}",
            "start": {
                "dateTime": start,
            },
            "end": {
                "dateTime": end,
            }
        }

        gdq_events.append(event)

    # determine events that don't need changing
    # discard duplicate requests from built gdq schedule
    # delete all existing events that need to be changed
    # send events that need to be updated
    events_to_del = [
        e for e in existing_events
        if is_outdated(e, gdq_events)
    ] if not settings.gcal["clear_all"] else existing_events

    print(f"Deleting {len(events_to_del)} outdated events...")
    for outdated_event in events_to_del:
        delete_event(service, outdated_event)

    existing_simp = [simplify_gcal(old_event) for old_event in existing_events]
    queries_to_send = [event for event in gdq_events if simplify_gcal(event) not in existing_simp]

    total_events = len(queries_to_send)
    print(f"{total_events} queries to send.")

    print("Consulting Google, please wait.")
    for x, event in enumerate(queries_to_send):

        add_event(service, event)
        # progress(x+1, total_events)

    print("")
    print("Done! Check your calendar!")
    print(f"Total Runtime: {timedelta(seconds=time()-exc_start)}")
    exit(0)
