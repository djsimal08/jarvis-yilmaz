from __future__ import annotations

import base64
import io
import wave
from typing import Any
from urllib.parse import quote

import httpx

from .secret_store import get_secret


class ProviderError(RuntimeError):
    pass


def _required_secret(name: str, label: str) -> str:
    value = get_secret(name)
    if not value:
        raise ProviderError(f"{label} API anahtarı kayıtlı değil.")
    return value


def pcm_to_wav(pcm: bytes, sample_rate: int = 24000) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return output.getvalue()


def _find_audio_data(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("output_audio", "outputAudio"):
            audio = value.get(key)
            if isinstance(audio, dict) and isinstance(audio.get("data"), str):
                return audio["data"]
        if value.get("type") == "audio" and isinstance(value.get("data"), str):
            return value["data"]
        for item in value.values():
            found = _find_audio_data(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_audio_data(item)
            if found:
                return found
    return None


async def synthesize(config: dict[str, Any], text: str) -> tuple[bytes, str]:
    provider = str(config.get("tts_provider", "windows"))
    clean = text.strip()
    if not clean:
        raise ProviderError("Seslendirilecek metin boş.")
    if len(clean) > 4000:
        clean = clean[:4000]

    if provider == "openai":
        key = _required_secret("openai_api_key", "OpenAI")
        payload: dict[str, Any] = {
            "model": config.get("openai_tts_model", "gpt-4o-mini-tts"),
            "voice": config.get("openai_tts_voice", "marin"),
            "input": clean,
            "response_format": "mp3",
        }
        instructions = str(config.get("tts_instructions", "")).strip()
        if instructions:
            payload["instructions"] = instructions[:500]
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            if not response.is_success:
                raise ProviderError("OpenAI sesi üretilemedi. Anahtarı, modeli ve API bakiyesini kontrol edin.")
            return response.content, "audio/mpeg"

    if provider == "gemini":
        key = _required_secret("gemini_api_key", "Gemini")
        payload = {
            "model": config.get("gemini_tts_model", "gemini-3.1-flash-tts-preview"),
            "input": f"Doğal ve sakin Türkçe konuş: {clean}",
            "response_format": {"type": "audio"},
            "generation_config": {
                "speech_config": [{"voice": config.get("gemini_tts_voice", "Kore"), "language": "tr-TR"}]
            },
        }
        async with httpx.AsyncClient(timeout=75) as client:
            response = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json=payload,
            )
            if not response.is_success:
                raise ProviderError("Gemini sesi üretilemedi. Anahtarı, modeli ve kotayı kontrol edin.")
            encoded = _find_audio_data(response.json())
            if not encoded:
                raise ProviderError("Gemini yanıtında ses verisi bulunamadı.")
            return pcm_to_wav(base64.b64decode(encoded)), "audio/wav"

    if provider == "elevenlabs":
        key = _required_secret("elevenlabs_api_key", "ElevenLabs")
        voice_id = str(config.get("elevenlabs_voice_id", "")).strip()
        if not voice_id:
            raise ProviderError("ElevenLabs voice ID girilmedi.")
        model = str(config.get("elevenlabs_model", "eleven_multilingual_v2")).strip()
        async with httpx.AsyncClient(timeout=75) as client:
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{quote(voice_id, safe='')}",
                params={"output_format": "mp3_44100_128"},
                headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                json={"text": clean, "model_id": model},
            )
            if not response.is_success:
                raise ProviderError("ElevenLabs sesi üretilemedi. Anahtarı, voice ID'yi ve kotayı kontrol edin.")
            return response.content, "audio/mpeg"

    raise ProviderError("Seçilen ses sağlayıcısı sunucu üzerinden ses üretmiyor.")
