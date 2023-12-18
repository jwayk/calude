import re
import json
from time import time
from datetime import (
    datetime,
    timedelta
)
import pickle
import os

import urllib3
from bs4 import BeautifulSoup
import backoff
import pytz
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import settings


if __name__ == "__main__":

    http = urllib3.PoolManager()

    response = http.request("GET", "https://gamesdonequick.com/schedule")
    soup = BeautifulSoup(response.data, "html.parser")

    header = soup.find("h1")
    year = re.search(r".*?(\d{4})(?:\sOnline)?\sSchedule", header.text).group(1)

    run_table = soup.find("table", {"id": "runTable"}).find("tbody")
    table_rows = run_table.find_all("tr")

    day = None
    events = []
    for row in table_rows:

        row_class = row.get("class", [])

        if "day-split" in row_class:
            day = row.find("td").text
            # print(day)
            continue

        if not row_class or (len(row_class) == 1 and "bg-info" in row_class):
            time, game, runner, setup = [data.text for data in row.find_all("td")]
            continue

        if "second-row" in row_class:

            runtime, run_type, commentary = [data.text for data in row.find_all("td")]
            events.append(
                {
                    "day": day,
                    "start": time,
                    "game": game,
                    "runner": runner,
                    "runtime": runtime,
                    "run_type": run_type,
                    "commentary": commentary,
                }
            )

    print(len(events))

    # print(json.dumps(events, indent=4))
    # print(soup.prettify())
    # print(header.text)
    # print(run_table)
