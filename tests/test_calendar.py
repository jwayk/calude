from interfaces import CalendarInterface
import settings


def test_retrieval():
    calendar = CalendarInterface(settings.calendar_id)
    events = calendar.get_all_events()
    assert len(events)
