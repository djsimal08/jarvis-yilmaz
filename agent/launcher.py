from __future__ import annotations

import threading
import time

import uvicorn
import webview

from agent.main import CONFIG, app


HOST = str(CONFIG.get("host", "127.0.0.1"))
PORT = int(CONFIG.get("port", 8765))


def main() -> None:
    server = uvicorn.Server(
        uvicorn.Config(app, host=HOST, port=PORT, log_level="warning", access_log=False)
    )
    thread = threading.Thread(target=server.run, name="jarvis-local-agent", daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.1)
    if not server.started:
        raise RuntimeError("JARVIS yerel ajanı başlatılamadı.")

    try:
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
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
