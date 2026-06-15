"""
🎙️ Transcriber — faster-whisper / whisper.cpp wrapper с конвертацией аудио и VAD
Вдохновлён Discorder (github.com/LaFa777/ai_slop_discord_voice_bot)

Два бэкенда:
- faster-whisper (по умолчанию) — Python-библиотека, VAD, beam_search
- whisper.cpp — лёгкий C++ бэкенд, меньше RAM

Особенности:
- convert_audio: PCM s16le 48kHz stereo → float32 mono
- transcribe: прямой проход numpy array (без temp-файлов)
- VAD-фильтр (только faster-whisper): вырезает тишину
- Ленивая загрузка модели (грузится при первом transcribe)
- Тайминги каждого этапа в логах
"""

import time
import numpy as np
from faster_whisper import WhisperModel


def _log(tag: str, msg: str):
    """Форматированный лог с таймстемпом"""
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] [{tag}] {msg}")


class Transcriber:
    """Умный transcriber: PCM → numpy → STT.
    Два бэкенда: faster-whisper (по умолчанию) или whisper.cpp.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        backend: str = "faster-whisper",
        whispercpp_model: str = "small",
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.backend = backend
        self.whispercpp_model = whispercpp_model
        self._faster_model = None
        self._whispercpp_instance = None

    # ===================== Загрузка faster-whisper =====================

    def _load_faster(self) -> WhisperModel:
        """Ленивая загрузка faster-whisper при первом transcribe"""
        if self._faster_model is None:
            t_start = time.time()
            _log(
                "WHISPER",
                f"Загружаю faster-whisper ({self.model_size}) "
                f"на {self.device} ({self.compute_type})...",
            )
            self._faster_model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            elapsed = time.time() - t_start
            _log("WHISPER", f"faster-whisper загружен за {elapsed:.1f}с")
        return self._faster_model

    # ===================== Загрузка whisper.cpp =====================

    def _load_whispercpp(self):
        """Ленивая загрузка whisper.cpp при первом transcribe"""
        if self._whispercpp_instance is None:
            t_start = time.time()
            _log("WHISPER", f"Загружаю whisper.cpp ({self.whispercpp_model})...")
            try:
                from whispercpp import Whisper
            except ImportError:
                raise ImportError(
                    "whisper.cpp не установлен. "
                    "Установи: pip install whisper-cpp-python"
                )
            self._whispercpp_instance = Whisper(self.whispercpp_model)
            elapsed = time.time() - t_start
            _log("WHISPER", f"whisper.cpp загружен за {elapsed:.1f}с")
        return self._whispercpp_instance

    # ===================== Конвертация аудио =====================

    @staticmethod
    def convert_audio(pcm48_stereo: bytes, label: str = "") -> np.ndarray:
        """
        PCM s16le 48kHz stereo → float32 mono [-1.0, 1.0]

        Берёт сырые PCM байты из sink (как есть, без WAV-заголовка),
        усредняет стерео в моно, нормализует.
        """
        t_start = time.time()
        audio_len_s = len(pcm48_stereo) / (48000 * 2 * 2)  # s16le stereo
        audio = np.frombuffer(pcm48_stereo, dtype=np.int16)
        # Стерео → моно (усредняем каналы)
        audio = audio.reshape(-1, 2).mean(axis=1).astype(np.float32)
        # Нормализация int16 → float32 [-1, 1]
        audio = audio / 32768.0
        elapsed = time.time() - t_start
        tag = f"WHISPER{label}"
        _log(tag, f"Конвертация: {audio_len_s:.1f}с аудио за {elapsed*1000:.0f}мс")
        return audio

    # ===================== Транскрипция =====================

    def transcribe(self, audio: np.ndarray, label: str = "") -> str:
        """Транскрибировать float32 mono → текст.
        Выбирает бэкенд по self.backend.
        """
        if self.backend == "whispercpp":
            return self._transcribe_whispercpp(audio, label)
        return self._transcribe_faster(audio, label)

    def _transcribe_faster(self, audio: np.ndarray, label: str = "") -> str:
        """
        faster-whisper:
        - Даунсемпл 48→16kHz (каждый 3-й сэмпл)
        - VAD фильтр: отсекает тишину
        - beam_size=5
        """
        t_start = time.time()
        model = self._load_faster()
        # 48 → 16 кГц (пропускаем 2 из 3)
        audio_16k = audio[::3]
        audio_len_s = len(audio) / 48000

        segments, _ = model.transcribe(
            audio_16k,
            beam_size=5,
            language="ru",
            vad_filter=True,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        elapsed = time.time() - t_start
        tag = f"WHISPER{label}"
        status = f"→ \"{text[:80]}\"" if text else "(пусто)"
        _log(tag, f"faster-whisper: {audio_len_s:.1f}с аудио за {elapsed:.1f}с {status}")
        return text

    def _transcribe_whispercpp(self, audio: np.ndarray, label: str = "") -> str:
        """
        whisper.cpp (через whisper-cpp-python):
        - Свой внутренний ресемплинг (не надо 48→16k руками)
        - Свой VAD / детектор тишины
        - Меньше RAM, быстрее на CPU
        """
        t_start = time.time()
        model = self._load_whispercpp()
        audio_len_s = len(audio) / 48000

        result = model.transcribe(audio)
        text = result.text.strip()
        elapsed = time.time() - t_start
        tag = f"WHISPER{label}"
        status = f"→ \"{text[:80]}\"" if text else "(пусто)"
        _log(tag, f"whisper.cpp: {audio_len_s:.1f}с аудио за {elapsed:.1f}с {status}")
        return text

    @property
    def current_backend(self) -> str:
        """Вернуть имя активного бэкенда"""
        return self.backend
