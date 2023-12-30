# calude

`calude` is a Python project designed to convert the [GamesDoneQuick schedule](https://gamesdonequick.com/schedule) to events in Google Calendar using BeautifulSoup4 and Google's Python API.

## Installation & Use

You will need a Google Cloud project and associated credentials to use the Google Calendar functionality. Here is a tutorial for [Google's Quickstart project](https://developers.google.com/drive/api/quickstart/python), which will walk you through the setup process. 

Once you have a project, download your `credentials.json` file from Google Workspace.

Then, clone this repository to your machine and run the following commands:

- `python -m venv venv`
- `source venv/bin/activate` (or `venv\Scripts\activate` on Windows)
- `pip install -r requirements.txt`

When your environment is set up, update `settings.py` with the ID of the Google Calendar you want the script to update. Note: the Google Cloud project you set up earlier will need access to this calendar.

After that you should be able to run the script with `python calude.py`
