import pytest

from soup import CalendarInterface
import settings


def test_retrieval():
    calendar = CalendarInterface(settings.gcal["id"])
    events = calendar._retrieve_events()
    assert len(events)
