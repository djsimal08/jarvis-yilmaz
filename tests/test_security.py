from pathlib import Path

import pytest

from agent.security import RiskLevel, SecurityError, classify, validate_user_path, validate_web_url


def test_irreversible_actions_need_final_confirmation():
    assert classify("file_delete") == RiskLevel.FINAL_CONFIRM
    assert classify("payment") == RiskLevel.FINAL_CONFIRM


def test_force_close_needs_confirmation():
    assert classify("force_close_process") == RiskLevel.CONFIRM


def test_read_only_actions_are_direct():
    assert classify("system_status") == RiskLevel.DIRECT
    assert classify("browser_read_page") == RiskLevel.DIRECT


def test_path_cannot_escape_allowed_root(tmp_path: Path):
    root = tmp_path / "Documents"
    root.mkdir()
    with pytest.raises(SecurityError):
        validate_user_path(tmp_path / "outside.txt", [root])


def test_unsafe_browser_scheme_is_rejected():
    with pytest.raises(SecurityError):
        validate_web_url("javascript:alert(1)")


def test_payment_click_needs_final_confirmation():
    assert classify("browser_click_text", {"text": "Ödeme yap"}) == RiskLevel.FINAL_CONFIRM


def test_publish_click_needs_confirmation():
    assert classify("browser_click_text", {"text": "Yayınla"}) == RiskLevel.CONFIRM
