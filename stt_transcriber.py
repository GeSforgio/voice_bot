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
import os
import tempfile
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
            model_path = self._ensure_whispercpp_model()
            _log("WHISPER", f"Загружаю whisper.cpp ({model_path})...")
            try:
                from whisper_cpp_python import Whisper
            except ImportError:
                raise ImportError(
                    "whisper_cpp_python не установлен. "
                    "Установи: pip install whisper-cpp-python"
                )
            self._whispercpp_instance = Whisper(
                model_path,
                n_threads=4,
            )
            elapsed = time.time() - t_start
            _log("WHISPER", f"whisper.cpp загружен за {elapsed:.1f}с")
        return self._whispercpp_instance

    def _ensure_whispercpp_model(self) -> str:
        """Проверить/скачать GGUF-модель whisper.cpp в .whisper_cache"""
        model_name = self.whispercpp_model  # "tiny", "base", "small"
        cache_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".whisper_cache"
        )
        os.makedirs(cache_dir, exist_ok=True)

        # Пробуем GGUF сначала, потом ggml (старый формат)
        for model_file in [f"ggml-{model_name}.bin", f"ggml-{model_name}-gguf.bin"]:
            local_path = os.path.join(cache_dir, model_file)
            if os.path.isfile(local_path):
                return local_path

        # GGUF не нашли — качаем
        model_file = f"ggml-{model_name}.bin"
        local_path = os.path.join(cache_dir, model_file)
        url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{model_file}"

        _log("WHISPER", f"Скачиваю модель: {url}")
        try:
            import urllib.request
            urllib.request.urlretrieve(url, local_path)
            _log("WHISPER", f"Модель скачана: {local_path}")
        except Exception as e:
            raise RuntimeError(f"Не удалось скачать модель whisper.cpp: {e}")

        return local_path

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
        whisper.cpp (через whisper_cpp_python):
        - Ресемплинг 48→16kHz
        - Пишет временный WAV, транскрайбит
        - Меньше RAM, быстрее на CPU
        """
        t_start = time.time()
        model = self._load_whispercpp()
        audio_len_s = len(audio) / 48000

        # Ресемпл 48→16kHz
        audio_16k = audio[::3]

        # Сохраняем во временный WAV (whisper.cpp может не принять numpy напрямую)
        tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp_wav.name
        tmp_wav.close()

        try:
            # int16 mono 16kHz
            samples = (audio_16k * 32767).clip(-32768, 32767).astype(np.int16)
            import wave
            with wave.open(tmp_path, "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(samples.tobytes())

            result = model.transcribe(tmp_path, language="ru")
            # result может быть dict или объект — универсально
            if isinstance(result, dict):
                text = result.get("text", "").strip()
            else:
                text = result.text.strip()
        except Exception as e:
            _log("WHISPER", f"whisper.cpp error: {e}")
            text = ""
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        elapsed = time.time() - t_start
        tag = f"WHISPER{label}"
        status = f"→ \"{text[:80]}\"" if text else "(пусто)"
        _log(tag, f"whisper.cpp: {audio_len_s:.1f}с аудио за {elapsed:.1f}с {status}")
        return text

    @property
    def current_backend(self) -> str:
        """Вернуть имя активного бэкенда"""
        return self.backend
