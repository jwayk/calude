from requests_html import HTML

from interfaces import HTMLInterface


gdq_schedule = HTMLInterface("https://gamesdonequick.com/schedule")


def test_html_retrieve():
    html = gdq_schedule._retrieve_html()
    assert type(html) == HTML
    assert html


def test_html_render():
    html = gdq_schedule.get_html()
    assert type(html) == bytes
    assert html
