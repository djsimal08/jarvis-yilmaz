from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class RiskLevel(IntEnum):
    DIRECT = 1
    CONFIRM = 2
    FINAL_CONFIRM = 3


DIRECT_TOOLS = {
    "open_application", "list_windows", "focus_window", "close_window",
    "browser_open_url", "browser_new_tab", "browser_list_tabs",
    "browser_read_page", "browser_find_text", "browser_media",
    "browser_click_text", "browser_click_nth_link", "browser_type_text",
    "browser_scroll", "browser_activate_relative_tab", "browser_close_tab",
    "browser_pin_tab", "browser_youtube_search_open", "set_volume", "system_status", "take_screenshot",
    "file_find", "file_open", "file_create", "create_folder",
}
CONFIRM_TOOLS = {
    "force_close_process", "file_move", "file_rename",
    "browser_submit_form", "browser_download", "install_application",
}
FINAL_CONFIRM_TOOLS = {
    "file_delete", "empty_recycle_bin", "payment", "purchase",
    "change_password", "delete_account", "admin_command", "format_disk",
}


@dataclass(slots=True)
class PlannedAction:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    risk: RiskLevel = RiskLevel.DIRECT

    def public_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": redact(self.arguments),
            "explanation": self.explanation,
            "risk": int(self.risk),
            "risk_name": self.risk.name,
        }


class SecurityError(ValueError):
    pass


def classify(tool: str, arguments: dict[str, Any] | None = None) -> RiskLevel:
    arguments = arguments or {}
    if tool == "browser_click_text":
        label = str(arguments.get("text", "")).casefold()
        if any(word in label for word in ("satın al", "öde", "ödeme", "transfer", "abonelik", "hesabı sil")):
            return RiskLevel.FINAL_CONFIRM
        if any(word in label for word in ("gönder", "yayınla", "paylaş", "kaydet", "onayla", "sipariş")):
            return RiskLevel.CONFIRM
    if tool in FINAL_CONFIRM_TOOLS:
        return RiskLevel.FINAL_CONFIRM
    if tool in CONFIRM_TOOLS:
        return RiskLevel.CONFIRM
    if tool in DIRECT_TOOLS:
        return RiskLevel.DIRECT
    return RiskLevel.FINAL_CONFIRM


def validate_web_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SecurityError("Yalnızca http/https internet adreslerine izin verilir.")
    return value.strip()


def allowed_roots(labels: list[str] | None = None) -> list[Path]:
    labels = labels or ["Desktop", "Documents", "Downloads"]
    home = Path.home().resolve()
    result: list[Path] = []
    for label in labels:
        clean = Path(label)
        if clean.is_absolute() or ".." in clean.parts:
            continue
        candidate = (home / clean).resolve()
        if candidate == home or home in candidate.parents:
            result.append(candidate)
    return result


def validate_user_path(value: str | Path, roots: list[Path], must_exist: bool = False) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = Path.home() / candidate
    candidate = candidate.resolve(strict=False)
    if not any(candidate == root or root in candidate.parents for root in roots):
        raise SecurityError("Bu konum izin verilen kullanıcı klasörlerinin dışında.")
    if must_exist and not candidate.exists():
        raise SecurityError("Dosya veya klasör bulunamadı.")
    return candidate


def redact(value: Any) -> Any:
    sensitive = {"password", "parola", "token", "api_key", "secret", "card", "cvv"}
    if isinstance(value, dict):
        return {
            key: "***" if key.casefold() in sensitive else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
