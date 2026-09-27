"""Голос: распознавание речи (faster-whisper, локально) и озвучка.

Озвучка: ElevenLabs, если в .env задан ELEVENLABS_API_KEY (при ошибке или исчерпанном
лимите — автоматически Edge TTS), иначе бесплатный Edge TTS.
"""

import logging
import os
import re
from pathlib import Path

import aiohttp
import edge_tts

log = logging.getLogger("assistant.voice")

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
TTS_VOICE = os.environ.get("TTS_VOICE", "ru-RU-DmitryNeural")
MAX_SPOKEN_CHARS = 3000

_whisper = None


def _get_whisper():
    # Модель загружается при первом голосовом сообщении (первый раз — скачивание ~500 МБ).
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel

        _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _whisper


def transcribe(audio_path: Path) -> str:
    segments, _info = _get_whisper().transcribe(str(audio_path), vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


def to_speech_text(markdown: str) -> str:
    """Убрать разметку, ссылки и таблицы, чтобы голос не зачитывал символы."""
    text = re.sub(r"```.*?```", " (код смотрите в тексте) ", markdown, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^\s*\|.*\|\s*$", "", text, flags=re.M)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)
    text = re.sub(r"[*_~>#]", "", text)
    text = re.sub(r"\n{2,}", ".\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) > MAX_SPOKEN_CHARS:
        text = text[:MAX_SPOKEN_CHARS].rsplit(" ", 1)[0] + "… Полный ответ — в тексте."
    return text


class ElevenLabsError(Exception):
    pass


async def elevenlabs_tts(text: str, out_path: Path) -> None:
    api_key = os.environ["ELEVENLABS_API_KEY"]
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID") or "JBFqnCBsd6RMkjVDRZzb"
    model = os.environ.get("ELEVENLABS_MODEL") or "eleven_multilingual_v2"
    base = os.environ.get("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io")
    url = f"{base}/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    payload = {"text": text, "model_id": model}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.post(url, json=payload, headers={"xi-api-key": api_key}) as res:
            if res.status != 200:
                raise ElevenLabsError(f"ElevenLabs {res.status}: {(await res.text())[:300]}")
            out_path.write_bytes(await res.read())


async def synthesize(text: str, out_path: Path, voice: str | None = None) -> bool:
    """Озвучить текст в MP3. Возвращает False, если озвучивать нечего."""
    spoken = to_speech_text(text)
    if not spoken:
        return False
    if os.environ.get("ELEVENLABS_API_KEY"):
        try:
            await elevenlabs_tts(spoken, out_path)
            return True
        except Exception as e:
            # Лимит закончился или сеть недоступна — не молчим, озвучиваем бесплатно.
            log.warning("ElevenLabs недоступен, озвучиваю через Edge TTS: %s", e)
    await edge_tts.Communicate(spoken, voice or os.environ.get("TTS_VOICE", TTS_VOICE)).save(str(out_path))
    return True
