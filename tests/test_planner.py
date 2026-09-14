import asyncio

from agent.planner import Planner
from agent.security import RiskLevel


def plan(command: str):
    planner = Planner({"enable_local_llm": False})
    return asyncio.run(planner.plan(command))


def test_open_chrome():
    action = plan("Chrome'u aç")
    assert action.tool == "open_application"
    assert action.arguments["name"] == "Google Chrome"


def test_volume():
    action = plan("Ses seviyesini yüzde 30 yap")
    assert action.tool == "set_volume"
    assert action.arguments["percent"] == 30


def test_google_search():
    action = plan("Google'da PUBG Mobile güncellemesini ara")
    assert action.tool == "browser_open_url"
    assert "google.com/search" in action.arguments["url"]


def test_create_desktop_folder():
    action = plan("Masaüstünde Jarvis Test klasörü oluştur")
    assert action.tool == "create_folder"
    assert action.arguments["path"].startswith("Desktop/")


def test_unknown_command_does_not_execute():
    action = plan("Şunu hallet")
    assert action.tool == "clarify"
    assert action.risk == RiskLevel.FINAL_CONFIRM


def test_second_search_result():
    action = plan("İkinci sonuca gir")
    assert action.tool == "browser_click_nth_link"
    assert action.arguments["index"] == 2


def test_previous_tab():
    action = plan("Bir önceki sekmeye dön")
    assert action.tool == "browser_activate_relative_tab"
    assert action.arguments["offset"] == -1


def test_publish_click_requires_confirmation():
    action = plan("Yayınla butonuna bas")
    assert action.tool == "browser_click_text"
    assert action.risk == RiskLevel.CONFIRM


def test_youtube_search_opens_first_video():
    action = plan("YouTube'dan Hababam Sınıfı'nı aç")
    assert action.tool == "browser_youtube_search_open"
    assert "Hababam" in action.arguments["query"]
