from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import webview


ROOT = Path(__file__).resolve().parent.parent
HOST, PORT = "127.0.0.1", 8765


def wait_for_server(timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("JARVIS yerel ajanı başlatılamadı.")


def main() -> None:
    server = subprocess.Popen(
        [sys.executable, "-m", "agent.main"],
        cwd=ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        wait_for_server()
        webview.create_window(
            "JARVIS — Yerel Kontrol Merkezi",
            f"http://{HOST}:{PORT}",
            width=1500,
            height=900,
            min_size=(1100, 700),
            background_color="#030812",
        )
        webview.start(debug=False, private_mode=True)
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
