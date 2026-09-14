from __future__ import annotations

import webview


def main() -> None:
    webview.create_window(
        "JARVIS Orb",
        "http://127.0.0.1:8765/mini",
        width=250,
        height=250,
        frameless=True,
        easy_drag=True,
        on_top=True,
        transparent=True,
        background_color="#00000000",
    )
    webview.start(debug=False, private_mode=True)


if __name__ == "__main__":
    main()
