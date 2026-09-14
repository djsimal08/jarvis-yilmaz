from __future__ import annotations

import os
import shutil
import subprocess
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
from PIL import ImageGrab
from send2trash import send2trash

from .security import SecurityError, validate_user_path, validate_web_url


class ToolError(RuntimeError):
    pass


class WindowsTools:
    def __init__(self, roots: list[Path], extra_apps: dict[str, str] | None = None) -> None:
        self.roots = roots
        self.extra_apps = {k.casefold(): v for k, v in (extra_apps or {}).items()}

    @staticmethod
    def _require_windows() -> None:
        if os.name != "nt":
            raise ToolError("Bu araç yalnızca Windows üzerinde çalışır.")

    def _find_application(self, requested: str) -> str:
        self._require_windows()
        name = requested.strip().casefold()
        aliases = {
            "chrome": "chrome.exe",
            "google chrome": "chrome.exe",
            "not defteri": "notepad.exe",
            "notepad": "notepad.exe",
            "dosya gezgini": "explorer.exe",
            "gezgin": "explorer.exe",
            "görev yöneticisi": "taskmgr.exe",
            "task manager": "taskmgr.exe",
            "hesap makinesi": "calc.exe",
            "paint": "mspaint.exe",
            "ldplayer": "dnplayer.exe",
        }
        if name in self.extra_apps:
            candidate = Path(os.path.expandvars(self.extra_apps[name]))
            if candidate.is_file():
                return str(candidate)
        executable = aliases.get(name, requested.strip())
        found = shutil.which(executable)
        if found:
            return found

        candidates = []
        program_files = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
        if executable.casefold() == "chrome.exe":
            for root in program_files:
                if root:
                    candidates.append(Path(root) / "Google/Chrome/Application/chrome.exe")
        if executable.casefold() == "dnplayer.exe":
            candidates += [
                Path("C:/LDPlayer/LDPlayer9/dnplayer.exe"),
                Path("C:/Program Files/LDPlayer/LDPlayer9/dnplayer.exe"),
            ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        raise ToolError(f"Uygulama bulunamadı: {requested}")

    def open_application(self, name: str) -> dict[str, Any]:
        if name.strip().casefold() in {"ayarlar", "windows ayarları"}:
            self._require_windows()
            os.startfile("ms-settings:")
            return {"opened": True, "application": "Windows Ayarları"}
        executable = self._find_application(name)
        process = subprocess.Popen([executable], close_fds=True)
        time.sleep(0.8)
        return {"opened": process.poll() is None, "application": name, "pid": process.pid}

    def browser_open_url(self, url: str, new_tab: bool = True) -> dict[str, Any]:
        url = validate_web_url(url)
        try:
            chrome = self._find_application("chrome")
            args = [chrome, "--new-tab" if new_tab else "--new-window", url]
            process = subprocess.Popen(args, close_fds=True)
            return {"opened": process.poll() is None, "url": url, "pid": process.pid}
        except ToolError:
            opened = webbrowser.open_new_tab(url) if new_tab else webbrowser.open_new(url)
            return {"opened": bool(opened), "url": url}

    def list_windows(self) -> dict[str, Any]:
        self._require_windows()
        import win32gui

        windows: list[dict[str, Any]] = []

        def collect(hwnd: int, _: Any) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd).strip()
            if not title:
                return
            _, pid = __import__("win32process").GetWindowThreadProcessId(hwnd)
            try:
                process_name = psutil.Process(pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                process_name = "Bilinmiyor"
            windows.append({"handle": hwnd, "title": title, "pid": pid, "process": process_name})

        win32gui.EnumWindows(collect, None)
        return {"count": len(windows), "windows": windows[:100]}

    def active_window(self) -> dict[str, Any]:
        self._require_windows()
        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return {"handle": hwnd, "title": title, "pid": pid}

    def focus_window(self, title: str) -> dict[str, Any]:
        self._require_windows()
        import win32con
        import win32gui

        needle = title.casefold()
        match: int | None = None

        def find(hwnd: int, _: Any) -> None:
            nonlocal match
            if match is None and win32gui.IsWindowVisible(hwnd):
                if needle in win32gui.GetWindowText(hwnd).casefold():
                    match = hwnd

        win32gui.EnumWindows(find, None)
        if match is None:
            raise ToolError(f"Pencere bulunamadı: {title}")
        win32gui.ShowWindow(match, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(match)
        return {"focused": True, "title": win32gui.GetWindowText(match)}

    def close_window(self, title: str) -> dict[str, Any]:
        self._require_windows()
        import win32con
        import win32gui

        needle = title.casefold()
        closed: list[str] = []

        def close(hwnd: int, _: Any) -> None:
            current = win32gui.GetWindowText(hwnd)
            if win32gui.IsWindowVisible(hwnd) and needle in current.casefold():
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                closed.append(current)

        win32gui.EnumWindows(close, None)
        if not closed:
            raise ToolError(f"Kapatılacak pencere bulunamadı: {title}")
        return {"closed": True, "windows": closed}

    def force_close_process(self, pid: int) -> dict[str, Any]:
        self._require_windows()
        process = psutil.Process(int(pid))
        name = process.name()
        process.kill()
        process.wait(timeout=5)
        return {"terminated": True, "pid": pid, "process": name}

    def set_volume(self, percent: int) -> dict[str, Any]:
        self._require_windows()
        value = max(0, min(int(percent), 100))
        try:
            from pycaw.pycaw import AudioUtilities
            device = AudioUtilities.GetSpeakers()
            endpoint = device.EndpointVolume
            endpoint.SetMasterVolumeLevelScalar(value / 100.0, None)
        except Exception as exc:
            raise ToolError(f"Ses seviyesi değiştirilemedi: {exc}") from exc
        return {"changed": True, "volume": value}

    def system_status(self) -> dict[str, Any]:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path.home().anchor or "/"))
        battery = psutil.sensors_battery()
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.15),
            "ram_percent": memory.percent,
            "ram_used_gb": round(memory.used / 1024**3, 1),
            "ram_total_gb": round(memory.total / 1024**3, 1),
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / 1024**3, 1),
            "battery_percent": battery.percent if battery else None,
            "network_connected": any(stats.isup for stats in psutil.net_if_stats().values()),
            "process_count": len(psutil.pids()),
        }

    def take_screenshot(self, filename: str | None = None) -> dict[str, Any]:
        self._require_windows()
        folder = (Path.home() / "Desktop" / "JARVIS Ekran Görüntüleri").resolve()
        folder.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename or datetime.now().strftime("jarvis_%Y%m%d_%H%M%S.png")).name
        if not safe_name.casefold().endswith(".png"):
            safe_name += ".png"
        destination = validate_user_path(folder / safe_name, self.roots)
        ImageGrab.grab(all_screens=True).save(destination, "PNG")
        return {"saved": destination.exists(), "path": str(destination)}

    def create_folder(self, path: str) -> dict[str, Any]:
        destination = validate_user_path(path, self.roots)
        destination.mkdir(parents=True, exist_ok=False)
        return {"created": destination.is_dir(), "path": str(destination)}

    def file_create(self, path: str, text: str = "") -> dict[str, Any]:
        destination = validate_user_path(path, self.roots)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        return {"created": destination.is_file(), "path": str(destination), "bytes": destination.stat().st_size}

    def file_open(self, path: str) -> dict[str, Any]:
        self._require_windows()
        source = validate_user_path(path, self.roots, must_exist=True)
        os.startfile(source)
        return {"opened": True, "path": str(source)}

    def file_find(self, query: str, limit: int = 30) -> dict[str, Any]:
        needle = query.casefold()
        matches: list[dict[str, Any]] = []
        for root in self.roots:
            if not root.exists():
                continue
            for current, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for name in files + dirs:
                    if needle in name.casefold():
                        path = Path(current) / name
                        matches.append({"name": name, "path": str(path), "is_dir": path.is_dir()})
                        if len(matches) >= limit:
                            return {"count": len(matches), "matches": matches}
        return {"count": len(matches), "matches": matches}

    def file_move(self, source: str, destination: str) -> dict[str, Any]:
        src = validate_user_path(source, self.roots, must_exist=True)
        dst = validate_user_path(destination, self.roots)
        moved = Path(shutil.move(str(src), str(dst)))
        return {"moved": moved.exists(), "from": str(src), "to": str(moved)}

    def file_rename(self, source: str, new_name: str) -> dict[str, Any]:
        src = validate_user_path(source, self.roots, must_exist=True)
        if Path(new_name).name != new_name:
            raise SecurityError("Yeni ad yalnızca dosya/klasör adı olmalıdır.")
        dst = validate_user_path(src.with_name(new_name), self.roots)
        src.rename(dst)
        return {"renamed": dst.exists(), "from": str(src), "to": str(dst)}

    def file_delete(self, path: str) -> dict[str, Any]:
        source = validate_user_path(path, self.roots, must_exist=True)
        send2trash(str(source))
        return {"recycled": not source.exists(), "path": str(source)}
