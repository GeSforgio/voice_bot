"""
🎙️ Transcriber — faster-whisper wrapper с конвертацией аудио и VAD
Вдохновлён Discorder (github.com/LaFa777/ai_slop_discord_voice_bot)

Особенности:
- convert_audio: PCM s16le 48kHz stereo → float32 mono
- transcribe: прямой проход numpy array (без temp-файлов)
- VAD-фильтр: вырезает тишину, ускоряет распознавание
- Ленивая загрузка модели (грузится при первом transcribe)
"""

import numpy as np
from faster_whisper import WhisperModel


class Transcriber:
    """Умный transcriber: PCM → numpy → whisper с VAD"""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    # ===================== Загрузка модели =====================

    def _load(self) -> WhisperModel:
        """Ленивая загрузка модели при первом transcribe"""
        if self._model is None:
            print(
                f"[WHISPER] Загружаю Whisper ({self.model_size}) "
                f"на {self.device} ({self.compute_type})..."
            )
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            print("[WHISPER] OK!")
        return self._model

    # ===================== Конвертация аудио =====================

    @staticmethod
    def convert_audio(pcm48_stereo: bytes) -> np.ndarray:
        """
        PCM s16le 48kHz stereo → float32 mono [-1.0, 1.0]

        Берёт сырые PCM байты из sink (как есть, без WAV-заголовка),
        усредняет стерео в моно, нормализует.
        """
        audio = np.frombuffer(pcm48_stereo, dtype=np.int16)
        # Стерео → моно (усредняем каналы)
        audio = audio.reshape(-1, 2).mean(axis=1).astype(np.float32)
        # Нормализация int16 → float32 [-1, 1]
        audio = audio / 32768.0
        return audio

    # ===================== Транскрипция =====================

    def transcribe(self, audio: np.ndarray) -> str:
        """
        Транскрибировать float32 mono массив → текст

        - Даунсемпл 48→16kHz (каждый 3-й сэмпл)
        - VAD фильтр: отсекает тишину, лучше качество
        - beam_size=5: баланс скорость/точность
        """
        model = self._load()
        # 48 → 16 кГц (пропускаем 2 из 3)
        audio_16k = audio[::3]

        segments, _ = model.transcribe(
            audio_16k,
            beam_size=5,
            language="ru",
            vad_filter=True,
        )
        return " ".join(s.text.strip() for s in segments).strip()
