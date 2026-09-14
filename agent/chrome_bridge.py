from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import WebSocket


class ChromeUnavailable(RuntimeError):
    pass


class ChromeBridge:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.token_path = data_dir / "chrome-token.txt"
        self.token = self._load_or_create_token()
        self.pair_code = self._new_pair_code()
        self.pair_expires = time.monotonic() + 600
        self.socket: WebSocket | None = None
        self.pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self.tabs: list[dict[str, Any]] = []

    def _load_or_create_token(self) -> str:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.token_path.exists():
            return self.token_path.read_text(encoding="utf-8").strip()
        value = secrets.token_urlsafe(32)
        self.token_path.write_text(value, encoding="utf-8")
        return value

    @staticmethod
    def _new_pair_code() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def pairing_status(self) -> dict[str, Any]:
        if time.monotonic() >= self.pair_expires:
            self.pair_code = self._new_pair_code()
            self.pair_expires = time.monotonic() + 600
        return {"code": self.pair_code, "expires_seconds": max(0, int(self.pair_expires - time.monotonic()))}

    def pair(self, code: str) -> str:
        status = self.pairing_status()
        if not secrets.compare_digest(code.strip(), status["code"]):
            raise ValueError("Eşleştirme kodu yanlış.")
        self.pair_code = self._new_pair_code()
        self.pair_expires = time.monotonic() + 600
        return self.token

    @property
    def connected(self) -> bool:
        return self.socket is not None

    async def attach(self, websocket: WebSocket) -> None:
        self.socket = websocket
        try:
            while True:
                payload = json.loads(await websocket.receive_text())
                kind = payload.get("type")
                if kind == "result":
                    request_id = str(payload.get("id", ""))
                    future = self.pending.pop(request_id, None)
                    if future and not future.done():
                        future.set_result(payload)
                elif kind == "tabs":
                    self.tabs = payload.get("tabs", [])[:100]
                elif kind == "ping":
                    await websocket.send_json({"type": "pong"})
        finally:
            if self.socket is websocket:
                self.socket = None
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(ChromeUnavailable("Chrome bağlantısı kesildi."))
            self.pending.clear()

    async def execute(self, action: str, arguments: dict[str, Any] | None = None, timeout: float = 15) -> dict[str, Any]:
        if not self.socket:
            raise ChromeUnavailable("Chrome eklentisi bağlı değil.")
        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.pending[request_id] = future
        try:
            await self.socket.send_json({
                "type": "command",
                "id": request_id,
                "action": action,
                "arguments": arguments or {},
            })
            result = await asyncio.wait_for(future, timeout=timeout)
        except Exception:
            self.pending.pop(request_id, None)
            raise
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "Chrome işlemi başarısız.")
        return result.get("result") or {}
