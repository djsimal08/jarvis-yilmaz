from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

from .secret_store import get_secret
from .security import PlannedAction, classify


ALLOWED_TOOLS = {
    "open_application", "list_windows", "focus_window", "close_window",
    "force_close_process", "browser_open_url", "browser_new_tab",
    "browser_list_tabs", "browser_read_page", "browser_find_text",
    "browser_click_text", "browser_click_nth_link", "browser_type_text",
    "browser_scroll", "browser_activate_relative_tab", "browser_close_tab",
    "browser_pin_tab", "browser_media", "set_volume", "system_status", "take_screenshot",
    "file_find", "file_open", "file_create", "create_folder",
    "file_move", "file_rename", "file_delete",
}

TOOL_GUIDE = """
Return only one JSON object: {"tool":"...", "arguments":{}, "explanation":"..."}.
Allowed tools:
open_application {name}; list_windows {}; focus_window {title}; close_window {title};
force_close_process {pid}; browser_open_url {url}; browser_new_tab {url?};
browser_list_tabs {}; browser_read_page {summarize?}; browser_find_text {text};
browser_click_text {text}; browser_click_nth_link {index}; browser_type_text {text};
browser_scroll {amount}; browser_activate_relative_tab {offset};
browser_close_tab {}; browser_pin_tab {pinned};
browser_media {command: play|pause|mute|unmute|fullscreen};
set_volume {percent}; system_status {}; take_screenshot {filename?};
file_find {query}; file_open {path}; file_create {path,text};
create_folder {path}; file_move {source,destination}; file_rename {source,new_name};
file_delete {path}.
Never invent a file path, PID, URL, application or missing user detail. If unclear return
{"tool":"clarify","arguments":{"question":"short Turkish question"},"explanation":""}.
"""


class Planner:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def plan(self, command: str) -> PlannedAction:
        command = command.strip()
        if not command:
            return self._action("clarify", {"question": "Hangi işlemi yapmamı istiyorsunuz?"}, "")
        deterministic = self._deterministic(command)
        if deterministic:
            return deterministic
        if self._can_use_openai(command):
            planned = await self._openai(command)
            if planned:
                return planned
        if self.config.get("enable_local_llm", True):
            planned = await self._ollama(command)
            if planned:
                return planned
        return self._action(
            "clarify",
            {"question": "Komutu güvenli biçimde anlayamadım. Biraz daha açık söyler misiniz?"},
            "",
        )

    def _action(self, tool: str, arguments: dict[str, Any], explanation: str) -> PlannedAction:
        return PlannedAction(tool=tool, arguments=arguments, explanation=explanation, risk=classify(tool, arguments))

    def _deterministic(self, raw: str) -> PlannedAction | None:
        text = raw.replace("İ", "i").replace("I", "ı").casefold().replace("’", "'")
        if text in {"dur", "iptal", "sus", "vazgeç"}:
            return self._action("cancel", {}, "Devam eden görevi durdur")
        if ("ram" in text and ("işlemci" in text or "cpu" in text)) or "sistem durumu" in text:
            return self._action("system_status", {}, "Sistem kullanımını göster")
        if "açık pencer" in text:
            return self._action("list_windows", {}, "Açık pencereleri listele")
        if "açık sekme" in text and any(word in text for word in ("say", "listele", "göster")):
            return self._action("browser_list_tabs", {}, "Gerçek Chrome sekmelerini oku")
        if "bir önceki sekme" in text or "önceki sekmeye" in text:
            return self._action("browser_activate_relative_tab", {"offset": -1}, "Önceki Chrome sekmesine geç")
        if "bir sonraki sekme" in text or "sonraki sekmeye" in text:
            return self._action("browser_activate_relative_tab", {"offset": 1}, "Sonraki Chrome sekmesine geç")
        if "bu sekmeyi kapat" in text or text == "sekmeyi kapat":
            return self._action("browser_close_tab", {}, "Aktif Chrome sekmesini kapat")
        if "sekmeyi sabitle" in text:
            return self._action("browser_pin_tab", {"pinned": True}, "Aktif Chrome sekmesini sabitle")
        if "sekmenin sabitlemesini kaldır" in text:
            return self._action("browser_pin_tab", {"pinned": False}, "Aktif Chrome sekmesinin sabitlemesini kaldır")
        if "sayfayı özetle" in text:
            return self._action("browser_read_page", {"summarize": True}, "Aktif sayfayı oku ve özetle")
        if "sayfayı oku" in text:
            return self._action("browser_read_page", {}, "Aktif sayfayı oku")
        match = re.search(r"bu sayfada\s+(.+?)\s+(?:yazan yeri )?bul", text)
        if match:
            return self._action("browser_find_text", {"text": match.group(1).strip()}, "Sayfadaki metni bul")
        ordinal = re.search(r"(?:^|\s)(birinci|ilk|ikinci|üçüncü|dördüncü|beşinci|[1-5]\.?)\s+(?:arama\s+)?sonuc", text)
        if ordinal and any(word in text for word in ("gir", "aç", "tıkla")):
            indexes = {"birinci": 1, "ilk": 1, "ikinci": 2, "üçüncü": 3, "dördüncü": 4, "beşinci": 5}
            token = ordinal.group(1).rstrip(".")
            index = indexes.get(token, int(token) if token.isdigit() else 1)
            return self._action("browser_click_nth_link", {"index": index}, f"{index}. görünür sonuca gir")
        match = re.search(r"(.+?)\s+(?:yazan\s+)?(?:yere|butona|bağlantıya)?\s*(?:tıkla|bas)$", text)
        if match:
            label = raw[match.start(1):match.end(1)].strip()
            return self._action("browser_click_text", {"text": label}, f"{label} öğesine tıkla")
        if "sayfayı aşağı" in text and ("kaydır" in text or "in" in text):
            return self._action("browser_scroll", {"amount": 700}, "Sayfayı aşağı kaydır")
        if "sayfayı yukarı" in text and ("kaydır" in text or "çık" in text):
            return self._action("browser_scroll", {"amount": -700}, "Sayfayı yukarı kaydır")
        match = re.search(r"(?:alana|kutusuna|buraya)\s+(.+?)\s+yaz$", text)
        if match:
            value = raw[match.start(1):match.end(1)].strip()
            return self._action("browser_type_text", {"text": value}, "Aktif form alanına metni yaz")
        if "videoyu durdur" in text or "videoyu duraklat" in text:
            return self._action("browser_media", {"command": "pause"}, "Aktif videoyu duraklat")
        if "videoyu oynat" in text or "videoyu devam ettir" in text:
            return self._action("browser_media", {"command": "play"}, "Aktif videoyu oynat")
        match = re.search(r"(?:sesi|ses seviyesini)\s+(?:yüzde\s*)?(\d{1,3})", text)
        if match:
            percent = max(0, min(int(match.group(1)), 100))
            return self._action("set_volume", {"percent": percent}, f"Ses seviyesini yüzde {percent} yap")
        if "sesi sustur" in text:
            return self._action("set_volume", {"percent": 0}, "Sesi sustur")
        if "ekran görüntü" in text and any(word in text for word in ("al", "kaydet")):
            return self._action("take_screenshot", {}, "Ekran görüntüsünü kaydet")
        match = re.search(r"masaüstünde\s+(.+?)(?:\s+diye)?\s+klasörü?\s+oluştur", text)
        if match:
            name = raw[match.start(1):match.end(1)].strip()
            return self._action("create_folder", {"path": f"Desktop/{name}"}, "Masaüstünde klasör oluştur")
        match = re.search(r"not defteri(?:'ni)?\s+aç(?:\s+ve)?\s+(.+?)\s+yaz", text)
        if match:
            value = raw[match.start(1):match.end(1)].strip()
            return self._action(
                "file_create",
                {"path": "Documents/JARVIS/not-defteri.txt", "text": value, "open_after": True},
                "Metni dosyaya yaz ve Not Defteri ile aç",
            )
        match = re.search(r"google(?:'da|da)?\s+(.+?)\s+ara", text)
        if match:
            query = raw[match.start(1):match.end(1)].strip()
            return self._action(
                "browser_open_url",
                {"url": "https://www.google.com/search?q=" + quote_plus(query)},
                "Google aramasını aç",
            )
        if "youtube" in text and ("aç" in text or "gir" in text):
            return self._action("browser_open_url", {"url": "https://www.youtube.com"}, "YouTube'u aç")
        if "yeni sekme" in text and ("aç" in text or "oluştur" in text):
            return self._action("browser_new_tab", {}, "Chrome'da yeni sekme aç")
        if text in {"chrome'u aç", "chrome aç", "google chrome'u aç", "google chrome aç"}:
            return self._action("open_application", {"name": "Google Chrome"}, "Chrome'u aç")
        match = re.search(r"(.+?)\s+penceresini\s+(?:öne getir|göster)", text)
        if match:
            return self._action("focus_window", {"title": match.group(1).strip()}, "Pencereyi öne getir")
        match = re.search(r"(.+?)\s+(?:programını|penceresini)?\s*kapat$", text)
        if match:
            return self._action("close_window", {"title": match.group(1).strip()}, "Pencereyi normal kapat")
        match = re.search(r"(?:dosya|klasör)\s+(.+?)\s+(?:bul|ara)$", text)
        if match:
            return self._action("file_find", {"query": match.group(1).strip()}, "İzinli klasörlerde ara")
        match = re.search(r"(.+?)(?:'ı|'i|'u|'ü|yı|yi|yu|yü)?\s+(?:aç|başlat)$", text)
        if match:
            name = raw[:match.end(1)].strip()
            return self._action("open_application", {"name": name}, f"{name} uygulamasını aç")
        return None

    def _can_use_openai(self, command: str) -> bool:
        if not self.config.get("openai_enabled", False) or not get_secret("openai_api_key"):
            return False
        consent = str(self.config.get("openai_consent", "local"))
        if consent == "all":
            return True
        if consent != "non_sensitive":
            return False
        normalized = command.replace("İ", "i").replace("I", "ı").casefold()
        sensitive = (
            "parola", "şifre", "kart", "cvv", "api key", "api anahtar", "token",
            "kimlik", "t.c.", "tc kimlik", "iban", "adres", "gizli", "dosya içeri",
        )
        return not any(word in normalized for word in sensitive) and "\\" not in command

    async def _openai(self, command: str) -> PlannedAction | None:
        api_key = get_secret("openai_api_key")
        if not api_key:
            return None
        model = str(self.config.get("openai_model", "gpt-5-mini")).strip() or "gpt-5-mini"
        prompt = (
            "You are a Turkish Windows command planner. Never claim an action happened. "
            "Choose exactly one allowlisted tool.\n" + TOOL_GUIDE
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "store": False,
                        "input": [
                            {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                            {"role": "user", "content": [{"type": "input_text", "text": command}]},
                        ],
                    },
                )
                response.raise_for_status()
                payload = response.json()
                pieces: list[str] = []
                for item in payload.get("output", []):
                    for content in item.get("content", []):
                        if content.get("type") in {"output_text", "text"}:
                            pieces.append(str(content.get("text", "")))
                raw = "".join(pieces).strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^\`\`\`(?:json)?\s*|\s*\`\`\`$", "", raw, flags=re.I)
                return self._validated_json(raw)
        except Exception:
            return None

    async def _ollama(self, command: str) -> PlannedAction | None:
        url = str(self.config.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/")
        model = str(self.config.get("ollama_model", "qwen3:4b"))
        prompt = "You are a Turkish Windows command planner.\n" + TOOL_GUIDE + "\nUser: " + command
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    url + "/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
                )
                response.raise_for_status()
                payload = response.json()
                return self._validated_json(payload.get("response", ""))
        except Exception:
            return None

    def _validated_json(self, raw: str) -> PlannedAction | None:
        try:
            data = json.loads(raw)
            tool = str(data["tool"])
            arguments = data.get("arguments") or {}
            if tool == "clarify":
                return self._action(tool, arguments, "")
            if tool not in ALLOWED_TOOLS or not isinstance(arguments, dict):
                return None
            return self._action(tool, arguments, str(data.get("explanation", "")))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
