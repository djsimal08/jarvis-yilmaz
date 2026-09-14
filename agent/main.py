from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

import psutil
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .chrome_bridge import ChromeBridge, ChromeUnavailable
from .history import HistoryStore
from .planner import Planner
from .security import PlannedAction, RiskLevel, allowed_roots
from .windows_tools import ToolError, WindowsTools


APP_ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = APP_ROOT / "dashboard"
DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "JarvisYilmaz"
CONFIG_PATH = DATA_ROOT / "config.json"
DATA_ROOT.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8765,
    "user_name": "Kullanıcı",
    "language": "tr-TR",
    "whisper_model": "small",
    "whisper_compute_type": "int8",
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "qwen3:4b",
    "enable_local_llm": True,
    "enable_voice_reply": True,
    "allowed_file_roots": ["Desktop", "Documents", "Downloads"],
    "extra_applications": {},
}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(DEFAULT_CONFIG)
    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        saved = {}
    return {**DEFAULT_CONFIG, **saved}


CONFIG = load_config()
ROOTS = allowed_roots(CONFIG.get("allowed_file_roots"))
WINDOWS = WindowsTools(ROOTS, CONFIG.get("extra_applications"))
HISTORY = HistoryStore(DATA_ROOT)
CHROME = ChromeBridge(DATA_ROOT)
PLANNER = Planner(CONFIG)

STATE: dict[str, Any] = {
    "mode": "IDLE",
    "current_task": None,
    "last_message": "JARVIS yerel ajanı başlatıldı.",
    "cancel_requested": False,
}
PENDING: dict[str, tuple[str, PlannedAction]] = {}
DASHBOARD_CLIENTS: set[WebSocket] = set()
WHISPER_MODEL: Any = None
WHISPER_LOCK = threading.Lock()
ORB_PROCESS: subprocess.Popen[Any] | None = None

app = FastAPI(title="JARVIS Local Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4000)


class ConfirmationRequest(BaseModel):
    approve: bool
    confirmation: str = ""


class PairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class ProfileRequest(BaseModel):
    user_name: str = Field(min_length=1, max_length=80)
    enable_voice_reply: bool = True


@app.middleware("http")
async def localhost_only(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0].strip("[]").casefold()
    client = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "localhost"} or client not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="JARVIS yalnızca bu bilgisayardan kullanılabilir.")
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'self'; "
        "connect-src 'self' ws://127.0.0.1:* ws://localhost:*; "
        "img-src 'self' data:; media-src 'self' blob:"
    )
    return response


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html")


@app.get("/mini")
async def mini() -> FileResponse:
    return FileResponse(STATIC_ROOT / "mini.html")


async def broadcast(payload: dict[str, Any]) -> None:
    stale: list[WebSocket] = []
    for socket in DASHBOARD_CLIENTS:
        try:
            await socket.send_json(payload)
        except Exception:
            stale.append(socket)
    for socket in stale:
        DASHBOARD_CLIENTS.discard(socket)


async def set_mode(mode: str, message: str = "") -> None:
    STATE["mode"] = mode
    if message:
        STATE["last_message"] = message
    await broadcast({"type": "state", "mode": mode, "message": STATE["last_message"]})


@app.websocket("/ws/dashboard")
async def dashboard_socket(websocket: WebSocket) -> None:
    client = websocket.client.host if websocket.client else ""
    if client not in {"127.0.0.1", "::1"}:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    DASHBOARD_CLIENTS.add(websocket)
    await websocket.send_json({"type": "state", **STATE})
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        DASHBOARD_CLIENTS.discard(websocket)


@app.websocket("/ws/chrome")
async def chrome_socket(websocket: WebSocket, token: str = "") -> None:
    client = websocket.client.host if websocket.client else ""
    if client not in {"127.0.0.1", "::1"} or not secrets.compare_digest(token, CHROME.token):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    await broadcast({"type": "connection", "chrome": True})
    try:
        await CHROME.attach(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await broadcast({"type": "connection", "chrome": False})


@app.post("/api/pair")
async def pair_extension(payload: PairRequest, request: Request) -> dict[str, Any]:
    origin = request.headers.get("origin", "")
    if origin and not origin.startswith("chrome-extension://"):
        raise HTTPException(status_code=403, detail="Bu işlem yalnızca Chrome eklentisinden yapılabilir.")
    try:
        token = CHROME.pair(payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"paired": True, "token": token}


@app.get("/api/status")
async def status() -> dict[str, Any]:
    try:
        system = await asyncio.to_thread(WINDOWS.system_status)
        active = await asyncio.to_thread(WINDOWS.active_window) if os.name == "nt" else {}
    except Exception as exc:
        system, active = {"error": str(exc)}, {}
    pair = CHROME.pairing_status()
    ollama_connected = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=0.8) as client:
            ollama_connected = (await client.get(str(CONFIG["ollama_url"]).rstrip("/") + "/api/tags")).is_success
    except Exception:
        pass
    return {
        "agent_connected": True,
        "chrome_connected": CHROME.connected,
        "ollama_connected": ollama_connected,
        "mode": STATE["mode"],
        "current_task": STATE["current_task"],
        "last_message": STATE["last_message"],
        "system": system,
        "active_window": active,
        "tabs": CHROME.tabs,
        "pairing": pair,
        "profile": {
            "user_name": CONFIG["user_name"],
            "enable_voice_reply": CONFIG["enable_voice_reply"],
        },
    }


@app.post("/api/command")
async def command(payload: CommandRequest) -> dict[str, Any]:
    task_id = uuid.uuid4().hex
    STATE["cancel_requested"] = False
    STATE["current_task"] = task_id
    await set_mode("UNDERSTANDING", "Komut anlaşılıyor…")
    action = await PLANNER.plan(payload.command)

    if action.tool == "cancel":
        return await cancel_all()
    if action.tool == "clarify":
        STATE["current_task"] = None
        question = str(action.arguments.get("question", "Komutu netleştirir misiniz?"))
        await set_mode("IDLE", question)
        return {"task_id": task_id, "status": "needs_clarification", "message": question}

    await set_mode("PLANNING", action.explanation or "Güvenlik seviyesi kontrol ediliyor…")
    HISTORY.write(task_id, payload.command, action.public_dict(), int(action.risk), "planned")

    if action.risk > RiskLevel.DIRECT:
        PENDING[task_id] = (payload.command, action)
        HISTORY.write(task_id, payload.command, action.public_dict(), int(action.risk), "approval_waiting")
        STATE["current_task"] = None
        await set_mode("IDLE", "Bu işlem onayınızı bekliyor.")
        return {
            "task_id": task_id,
            "status": "approval_waiting",
            "risk": int(action.risk),
            "action": action.public_dict(),
            "message": "İşlem uygulanmadı; onay bekleniyor.",
        }
    return await run_action(task_id, payload.command, action)


@app.post("/api/confirm/{task_id}")
async def confirm(task_id: str, payload: ConfirmationRequest) -> dict[str, Any]:
    pending = PENDING.pop(task_id, None)
    if not pending:
        raise HTTPException(status_code=404, detail="Onay bekleyen görev bulunamadı.")
    command_text, action = pending
    if not payload.approve:
        HISTORY.write(task_id, command_text, action.public_dict(), int(action.risk), "cancelled")
        await set_mode("IDLE", "İşlem iptal edildi.")
        return {"task_id": task_id, "status": "cancelled", "message": "İşlem uygulanmadı."}
    if action.risk == RiskLevel.FINAL_CONFIRM and payload.confirmation.strip().upper() != "ONAYLIYORUM":
        PENDING[task_id] = pending
        raise HTTPException(status_code=400, detail="Son onay için ONAYLIYORUM yazın.")
    return await run_action(task_id, command_text, action)


@app.post("/api/cancel")
async def cancel_all() -> dict[str, Any]:
    STATE["cancel_requested"] = True
    STATE["current_task"] = None
    for task_id, (command_text, action) in list(PENDING.items()):
        HISTORY.write(task_id, command_text, action.public_dict(), int(action.risk), "cancelled")
    PENDING.clear()
    await set_mode("IDLE", "Görevler güvenli noktada durduruldu.")
    return {"status": "cancelled", "message": STATE["last_message"]}


async def run_action(task_id: str, command_text: str, action: PlannedAction) -> dict[str, Any]:
    STATE["current_task"] = task_id
    await set_mode("EXECUTING", action.explanation or "İşlem uygulanıyor…")
    try:
        result = await execute(action)
        if STATE["cancel_requested"]:
            raise asyncio.CancelledError
        await set_mode("VERIFYING", "Sonuç gerçek sistem durumundan kontrol ediliyor…")
        verified = verify(action, result)
        status_name = "success" if verified else "partial"
        message = result_message(action, result, verified)
        HISTORY.write(task_id, command_text, action.public_dict(), int(action.risk), status_name, result)
        await set_mode("SPEAKING", message)
        STATE["current_task"] = None
        return {
            "task_id": task_id,
            "status": status_name,
            "verified": verified,
            "action": action.public_dict(),
            "result": result,
            "message": message,
        }
    except asyncio.CancelledError:
        HISTORY.write(task_id, command_text, action.public_dict(), int(action.risk), "cancelled")
        message = "İşlem iptal edildi."
    except (ToolError, ChromeUnavailable, RuntimeError, ValueError, OSError) as exc:
        message = str(exc)
        HISTORY.write(
            task_id, command_text, action.public_dict(), int(action.risk), "failed", {"error": message}
        )
    STATE["current_task"] = None
    await set_mode("IDLE", message)
    return {"task_id": task_id, "status": "failed", "verified": False, "message": message}


async def execute(action: PlannedAction) -> dict[str, Any]:
    tool, args = action.tool, dict(action.arguments)
    if tool == "browser_open_url":
        if CHROME.connected:
            return await CHROME.execute("openUrl", {"url": args["url"]})
        return await asyncio.to_thread(WINDOWS.browser_open_url, args["url"], True)
    if tool == "browser_new_tab":
        return await CHROME.execute("newTab", {"url": args.get("url")})
    if tool == "browser_list_tabs":
        return await CHROME.execute("listTabs")
    if tool == "browser_read_page":
        return await CHROME.execute("readPage", {"summarize": bool(args.get("summarize"))})
    if tool == "browser_find_text":
        return await CHROME.execute("findText", {"text": args["text"]})
    if tool == "browser_media":
        return await CHROME.execute("media", {"command": args["command"]})

    methods = {
        "open_application": WINDOWS.open_application,
        "list_windows": WINDOWS.list_windows,
        "focus_window": WINDOWS.focus_window,
        "close_window": WINDOWS.close_window,
        "force_close_process": WINDOWS.force_close_process,
        "set_volume": WINDOWS.set_volume,
        "system_status": WINDOWS.system_status,
        "take_screenshot": WINDOWS.take_screenshot,
        "file_find": WINDOWS.file_find,
        "file_open": WINDOWS.file_open,
        "file_create": WINDOWS.file_create,
        "create_folder": WINDOWS.create_folder,
        "file_move": WINDOWS.file_move,
        "file_rename": WINDOWS.file_rename,
        "file_delete": WINDOWS.file_delete,
    }
    method = methods.get(tool)
    if not method:
        raise ToolError(f"Desteklenmeyen araç: {tool}")
    open_after = bool(args.pop("open_after", False))
    result = await asyncio.to_thread(method, **args)
    if open_after and result.get("path"):
        await asyncio.to_thread(WINDOWS.file_open, result["path"])
        result["opened"] = True
    return result


def verify(action: PlannedAction, result: dict[str, Any]) -> bool:
    if result.get("error"):
        return False
    expected_keys = {
        "open_application": "opened",
        "browser_open_url": "opened",
        "set_volume": "changed",
        "take_screenshot": "saved",
        "create_folder": "created",
        "file_create": "created",
        "file_open": "opened",
        "file_move": "moved",
        "file_rename": "renamed",
        "file_delete": "recycled",
        "force_close_process": "terminated",
        "focus_window": "focused",
        "close_window": "closed",
    }
    key = expected_keys.get(action.tool)
    return bool(result.get(key)) if key else True


def result_message(action: PlannedAction, result: dict[str, Any], verified: bool) -> str:
    if not verified:
        return "İşlem uygulandı ancak sonuç tam olarak doğrulanamadı."
    tool = action.tool
    if tool == "set_volume":
        return f"Efendim, ses seviyesini yüzde {result.get('volume')} yaptım ve doğruladım."
    if tool == "system_status":
        return f"İşlemci yüzde {result.get('cpu_percent')}, RAM yüzde {result.get('ram_percent')} kullanılıyor."
    if tool == "browser_list_tabs":
        return f"Chrome'da {result.get('count', len(result.get('tabs', [])))} açık sekme var."
    if tool == "take_screenshot":
        return f"Ekran görüntüsünü kaydettim: {result.get('path')}"
    return "Efendim, işlem tamamlandı ve sonucu doğrulandı."


@app.get("/api/history")
async def history(limit: int = 30) -> dict[str, Any]:
    return {"items": HISTORY.recent(limit)}


@app.delete("/api/history")
async def clear_history() -> dict[str, Any]:
    HISTORY.clear()
    return {"cleared": True}


@app.post("/api/profile")
async def update_profile(payload: ProfileRequest) -> dict[str, Any]:
    CONFIG["user_name"] = payload.user_name.strip()
    CONFIG["enable_voice_reply"] = payload.enable_voice_reply
    CONFIG_PATH.write_text(json.dumps(CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": True}


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict[str, Any]:
    suffix = Path(audio.filename or "speech.webm").suffix or ".webm"
    data = await audio.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Ses kaydı çok büyük.")
    await set_mode("UNDERSTANDING", "Türkçe konuşma yazıya çevriliyor…")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(data)
        temp_path = handle.name
    try:
        text = await asyncio.to_thread(transcribe_local, temp_path)
        return {"text": text}
    finally:
        Path(temp_path).unlink(missing_ok=True)


def transcribe_local(path: str) -> str:
    global WHISPER_MODEL
    with WHISPER_LOCK:
        if WHISPER_MODEL is None:
            from faster_whisper import WhisperModel
            WHISPER_MODEL = WhisperModel(
                CONFIG["whisper_model"],
                device="cpu",
                compute_type=CONFIG["whisper_compute_type"],
            )
    segments, _ = WHISPER_MODEL.transcribe(path, language="tr", vad_filter=True)
    return " ".join(segment.text.strip() for segment in segments).strip()


@app.post("/api/mini-orb/{operation}")
async def mini_orb(operation: str) -> dict[str, Any]:
    global ORB_PROCESS
    if operation == "show":
        if ORB_PROCESS is None or ORB_PROCESS.poll() is not None:
            executable = Path(sys.executable).with_name("pythonw.exe") if os.name == "nt" else Path(sys.executable)
            ORB_PROCESS = subprocess.Popen([str(executable), "-m", "agent.orb"], cwd=APP_ROOT)
        return {"visible": True}
    if operation == "hide":
        if ORB_PROCESS and ORB_PROCESS.poll() is None:
            ORB_PROCESS.terminate()
        ORB_PROCESS = None
        return {"visible": False}
    raise HTTPException(status_code=400, detail="Geçersiz işlem.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=str(CONFIG["host"]), port=int(CONFIG["port"]), log_level="info")
