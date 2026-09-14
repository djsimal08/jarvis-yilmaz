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
