"""
🎙️ TTSEngine — менеджер TTS движков
Edge TTS (быстрый, облачный) или Silero TTS (локальный, естественный)

Команды в боте:
- !голос — статус
- !голос edge — переключить на Edge TTS
- !голос silero — переключить на Silero TTS (установит PyTorch при первом запуске)
- !голос список — показать доступные голоса текущего движка
- !голос voice [имя] — выбрать голос для текущего движка
"""

import os
import asyncio
import tempfile
import subprocess
import sys


# ============================================================
# Edge TTS — импорт лёгкий, всегда доступен
# ============================================================
_HAS_EDGE = True
try:
    import edge_tts
except ImportError:
    _HAS_EDGE = False


# ============================================================
# Silero голоса (список жёсткий, модель загружается лениво)
# ============================================================
SILERO_RU_VOICES = {
    "eugene": "🧑 Евгений (мужской, уверенный)",
    "aidar":   "🧑 Айдар (мужской, спокойный)",
    "baya":    "👩 Бая (женский, мягкий)",
    "kseniya": "👩 Ксения (женский, дружелюбный)",
    "xenia":   "👩 Ксения v2 (женский, чёткий)",
}


class TTSEngine:
    """Абстракция над TTS движками — можно переключать на лету"""

    def __init__(self):
        self.active = "edge"
        self.edge_voice = "ru-RU-DmitryNeural"
        self.silero_voice = "aidar"
        self._silero_model = None
        self._silero_loaded = False

    # ===================== Основной API =====================

    async def speak(self, text: str) -> tuple[str, bool]:
        """Сгенерировать TTS для текста.
        Возвращает (путь_к_временному_файлу, был_ли_это_silero).
        Файл самоудалится через garbage collector — играй сразу.
        """
        if self.active == "silero":
            path = await self._silero_generate(text)
            return path, True

        path = await self._edge_generate(text)
        return path, False

    # ===================== Управление =====================

    def set_engine(self, name: str) -> str:
        """Переключить движок. Возвращает сообщение для пользователя."""
        name = name.lower().strip()

        if name == "edge":
            if not _HAS_EDGE:
                return "❌ Edge TTS не установлен. Установи: `pip install edge-tts`"
            self.active = "edge"
            return f"✅ Переключён на Edge TTS: `{self.edge_voice}`"

        if name == "silero":
            self.active = "silero"
            voice_desc = SILERO_RU_VOICES.get(
                self.silero_voice, self.silero_voice
            )
            if not self._silero_loaded:
                return (
                    f"🔄 Переключён на Silero TTS: `{self.silero_voice}` ({voice_desc}).\n"
                    "   PyTorch загрузится при первом !чат или !скажи."
                )
            return f"✅ Silero TTS: `{self.silero_voice}` ({voice_desc})"

        return f"❌ Неизвестный движок «{name}». Доступны: edge, silero"

    def set_voice(self, voice: str) -> str:
        """Установить голос для текущего движка."""
        if self.active == "silero":
            if voice in SILERO_RU_VOICES:
                self.silero_voice = voice
                return f"✅ Голос Silero: `{voice}` ({SILERO_RU_VOICES[voice]})"
            else:
                avail = ", ".join(SILERO_RU_VOICES.keys())
                return f"❌ Нет голоса «{voice}». Доступны: {avail}"

        # Edge TTS — принимаем любой shorname
        self.edge_voice = voice
        return f"✅ Голос Edge TTS: `{voice}`"

    def get_status(self) -> str:
        """Вернуть строку статуса."""
        if self.active == "silero":
            desc = SILERO_RU_VOICES.get(self.silero_voice, self.silero_voice)
            loaded = "✅ модель загружена" if self._silero_loaded else "⏳ модель не загружена"
            return (
                f"🎙️ **Silero TTS** (локальный)\n"
                f"   Голос: `{self.silero_voice}` — {desc}\n"
                f"   Статус: {loaded}"
            )

        return (
            f"🎙️ **Edge TTS** (облачный)\n"
            f"   Голос: `{self.edge_voice}`\n"
            f"   Доступно русских голосов: 2 (Дмитрий, Светлана)"
        )

    def list_voices(self) -> str:
        """Вернуть список доступных голосов для текущего движка."""
        if self.active == "silero":
            lines = ["**🗣️ Silero TTS — русские голоса:**"]
            for name, desc in SILERO_RU_VOICES.items():
                marker = "✅" if name == self.silero_voice else "•"
                lines.append(f"  {marker} `{name}` — {desc}")
            return "\n".join(lines)

        # Edge — список фиксированный
        current = "✅" if self.edge_voice == "ru-RU-DmitryNeural" else "•"
        current2 = "✅" if self.edge_voice == "ru-RU-SvetlanaNeural" else "•"
        return (
            "**🗣️ Edge TTS — русские голоса:**\n"
            f"  {current} `ru-RU-DmitryNeural` 🧑 Дмитрий\n"
            f"  {current2} `ru-RU-SvetlanaNeural` 👩 Светлана"
        )

    # ===================== Edge TTS =====================

    async def _edge_generate(self, text: str) -> str:
        """Синтезировать через Edge TTS → вернуть путь к .mp3"""
        ext = ".mp3"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            tmp_path = f.name
        communicate = edge_tts.Communicate(text, self.edge_voice)
        await communicate.save(tmp_path)
        return tmp_path

    # ===================== Silero TTS =====================

    async def _silero_generate(self, text: str) -> str:
        """Синтезировать через Silero → вернуть путь к .wav"""
        ext = ".wav"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            tmp_path = f.name

        # Silero синхронный — запускаем в thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._silero_sync, text, tmp_path)
        return tmp_path

    def _silero_sync(self, text: str, output_path: str):
        """Синхронный синтез Silero (бежит в thread pool)"""
        # Ленивая загрузка модели при первом использовании
        if not self._silero_loaded:
            self._install_and_load_silero()

        audio = self._silero_model.apply_tts(
            text=text,
            speaker=self.silero_voice,
            sample_rate=48000,
            put_accent=True,
            put_yo=True,
        )

        # Сохраняем как WAV без дополнительных библиотек
        import struct
        import wave

        # Нормализуем float32 → int16
        samples = (audio.numpy().flatten() * 32767).clip(-32768, 32767).astype("int16")

        with wave.open(output_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(samples.tobytes())

    def _install_and_load_silero(self):
        """Установить PyTorch (если нет) и загрузить модель Silero"""
        # Проверяем PyTorch
        try:
            import torch  # noqa: F401
        except ImportError:
            print("[TTS] PyTorch не найден. Устанавливаю torch CPU-only...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "torch", "--quiet"]
            )
            print("[TTS] PyTorch установлен!")

        import torch

        device = torch.device("cpu")
        torch.set_num_threads(4)

        # Путь к кэшированному файлу модели
        model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".silero_cache")
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, "v5_ru.pt")

        if not os.path.isfile(model_path):
            print("[TTS] Скачиваю Silero модель v5_ru (~200 МБ)...")
            torch.hub.download_url_to_file(
                "https://models.silero.ai/models/tts/ru/v5_ru.pt",
                model_path,
            )
            print("[TTS] Модель скачана!")

        print("[TTS] Загружаю Silero модель...")
        model = torch.package.PackageImporter(model_path).load_pickle(
            "tts_models", "model"
        )
        model.to(device)
        self._silero_model = model
        self._silero_loaded = True
        print(f"[TTS] Silero загружен! Доступные голоса: {model.speakers}")
