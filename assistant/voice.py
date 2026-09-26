"""Голос: распознавание речи (faster-whisper, локально) и озвучка (Edge TTS, бесплатно)."""

import os
import re
from pathlib import Path

import edge_tts

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
TTS_VOICE = os.environ.get("TTS_VOICE", "ru-RU-SvetlanaNeural")
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


async def synthesize(text: str, out_path: Path, voice: str = TTS_VOICE) -> bool:
    """Озвучить текст в MP3. Возвращает False, если озвучивать нечего."""
    spoken = to_speech_text(text)
    if not spoken:
        return False
    await edge_tts.Communicate(spoken, voice).save(str(out_path))
    return True
