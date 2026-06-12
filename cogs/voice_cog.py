"""
🎤 VoiceCog — голосовые команды Пиздуна
!скажи, !выйди, !слушай, !хватит, !дежурь, !отдыхай

Переписано с PyCord → discord.py + voice_recv (Rapptz master)
- DAVE monkey-patch'и удалены — voice_recv обрабатывает DAVE нативно
- WaveSink → RecordingSink (voice_recv.AudioSink)
"""

import discord
from discord.ext import commands
from discord.ext import voice_recv
import asyncio
import os
import time
import numpy as np
from openai import OpenAI
import ai_config
import logging
from stt_transcriber import Transcriber

logger = logging.getLogger(__name__)


def _log(tag: str, msg: str):
    """Лог с таймстемпом для голосовых операций"""
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] [{tag}] {msg}")


# =====================================================================
# RecordingSink — кастомный sink для !слушай / !хватит
# Записывает всех говорящих в буфер, отдаёт PCM по запросу
# =====================================================================

class RecordingSink(voice_recv.AudioSink):
    """Sink для !слушай / !хватит. Копит PCM всех пользователей."""

    def __init__(self):
        super().__init__()
        self._buffers: dict[int, bytearray] = {}
        self._done = False

    def wants_opus(self) -> bool:
        return False

    def write(self, user: discord.User | discord.Member | None,
              data: voice_recv.VoiceData) -> None:
        """Пишем PCM данные в буфер пользователя"""
        if self._done or user is None or not data.pcm:
            return
        buf = self._buffers.get(user.id)
        if buf is not None:
            buf.extend(data.pcm)
        else:
            self._buffers[user.id] = bytearray(data.pcm)

    def get_audio(self) -> dict[int, bytes]:
        """Извлечь записанное аудио {user_id: pcm_bytes} и сбросить буферы"""
        result = {}
        for uid, buf in self._buffers.items():
            if buf:
                result[uid] = bytes(buf)
        self._buffers.clear()
        return result

    def stop_recording(self):
        """Остановить запись (вызывается из !хватит)"""
        self._done = True

    def cleanup(self) -> None:
        self._buffers.clear()


# =====================================================================
# DutySink — event-driven sink для режима дежурства
# Слушает всех, вызывает on_utterance когда кто-то договорил
# =====================================================================

class DutySink(voice_recv.AudioSink):
    """Sink для !дежурь. Событийный: реплика → on_utterance(member, pcm_bytes)"""

    def __init__(self, on_utterance):
        super().__init__()
        self._on_utterance = on_utterance
        self._buffers: dict[int, bytearray] = {}
        self.paused = False

    def wants_opus(self) -> bool:
        return False

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_start(self, member: discord.Member) -> None:
        self._buffers[member.id] = bytearray()

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member) -> None:
        audio = bytes(self._buffers.pop(member.id, bytearray()))
        if audio and not self.paused:
            loop = self.client and self.client.loop
            if loop and not loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    self._on_utterance(member, audio),
                    loop,
                )

    def write(self, user: discord.User | discord.Member | None,
              data: voice_recv.VoiceData) -> None:
        if self.paused or user is None or not data.pcm:
            return
        buf = self._buffers.get(user.id)
        if buf is not None:
            buf.extend(data.pcm)

    def cleanup(self) -> None:
        self._buffers.clear()


# =====================================================================
# VoiceCog
# =====================================================================

class VoiceCog(commands.Cog):
    """Голосовые команды Пиздуна"""

    def __init__(self, bot):
        self.bot = bot
        self.ai_client = OpenAI(
            api_key=ai_config.AI_API_KEY,
            base_url=ai_config.AI_ENDPOINT,
        )
        # Transcriber — ленивая загрузка whisper при первом вызове
        self.transcriber = Transcriber(
            model_size=ai_config.WHISPER_MODEL,
            device=ai_config.WHISPER_DEVICE,
            compute_type=ai_config.WHISPER_COMPUTE_TYPE,
        )
        # Фоновые задачи дежурства: {guild_id: asyncio.Task}
        self.duty_tasks: dict[int, asyncio.Task] = {}

    # ===================== УТИЛИТЫ =====================

    async def _ensure_voice(self, ctx) -> discord.VoiceClient:
        """Подключиться к голосовому каналу пользователя"""
        if not ctx.author.voice:
            raise commands.UserInputError("Ты не в войсе, брат! Зайди в канал сначала.")

        vc = ctx.voice_client
        if vc and vc.is_connected():
            if vc.channel.id != ctx.author.voice.channel.id:
                await vc.move_to(ctx.author.voice.channel)
            return vc

        vc = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
        _log("VOICE", f"Подключился к {ctx.author.voice.channel.name} (guild={ctx.guild.id})")
        return vc

    def _get_audio_data(self, sink: RecordingSink) -> dict[int, bytes]:
        """Извлечь PCM данные из синка"""
        return sink.get_audio()

    async def _transcribe(self, pcm_bytes: bytes) -> str | None:
        """
        Распознать речь через Transcriber (numpy, без temp-файлов).

        PCM s16le 48kHz stereo → convert_audio (float32 mono)
        → transcribe с VAD-фильтром.
        """
        try:
            audio = self.transcriber.convert_audio(pcm_bytes)
            text = self.transcriber.transcribe(audio)
            return text if text else None
        except Exception as e:
            _log("ERROR", f"Transcriber: {e}")
            return None

    async def _ask_deepseek(self, text: str, user_id: int = None) -> str:
        """Отправить текст в DeepSeek и получить ответ"""
        response = self.ai_client.chat.completions.create(
            model=ai_config.AI_MODEL,
            messages=[
                {"role": "system", "content": self.bot.prompt_manager.get_prompt(user_id)},
                {"role": "user", "content": text},
            ],
            max_tokens=ai_config.AI_MAX_TOKENS_VOICE,
            temperature=ai_config.AI_TEMPERATURE,
        )
        return response.choices[0].message.content

    async def _say_in_voice(self, vc: discord.VoiceClient, text: str):
        """Сгенерировать TTS и проиграть в войс"""
        async def _play_tts():
            tmp_path, _ = await self.bot.tts_engine.speak(text)

            # Ждём пока закончится предыдущее (если играем)
            while vc.is_playing():
                await asyncio.sleep(0.5)

            vc.play(
                discord.FFmpegPCMAudio(tmp_path),
                after=lambda e: os.unlink(tmp_path) if os.path.exists(tmp_path) else None,
            )

        try:
            await _play_tts()
        except Exception as e:
            _log("ERROR", f"TTS: {e}")

    # ===================== !скажи =====================

    @commands.command(name="скажи", aliases=["say", "speak"])
    async def say(self, ctx, *, text: str = None):
        """🎤 Пиздун говорит в войсе"""
        if not text:
            await ctx.send("**Пиздун:** А чё сказать-то? Напиши `!скажи [текст]`")
            return

        async with ctx.typing():
            try:
                vc = await self._ensure_voice(ctx)
            except commands.UserInputError:
                await ctx.send("**Пиздун:** Ты не в войсе, брат! Не починю.")
                return

            await ctx.send(f"**Пиздун:** *по рации* «{text[:100]}»")
            await self._say_in_voice(vc, text)

    # ===================== !голос =====================

    @commands.command(name="голос", aliases=["voice", "tts"])
    async def voice_settings(self, ctx, action: str = None, value: str = None):
        """🎙️ Управление TTS голосом

        !голос — показать текущий движок и голос
        !голос edge — переключить на Edge TTS
        !голос silero — переключить на Silero TTS
        !голос список — список голосов текущего движка
        !голос voice [имя] — выбрать голос
        """
        tts = self.bot.tts_engine

        if not action:
            await ctx.send(tts.get_status())
            return

        if action == "список":
            await ctx.send(tts.list_voices())
            return

        if action == "voice":
            if not value:
                await ctx.send("**Пиздун:** Напиши `!голос voice [имя_голоса]`")
                return
            msg = tts.set_voice(value)
            await ctx.send(f"**Пиздун:** {msg}")
            return

        if action in ("edge", "silero"):
            msg = tts.set_engine(action)
            await ctx.send(f"**Пиздун:** {msg}")
            return

        await ctx.send(
            "**Пиздун:** Не понял команду.\n"
            "Доступно: `!голос`, `!голос edge`, `!голос silero`, "
            "`!голос список`, `!голос voice [имя]`"
        )

    # ===================== !выйди =====================

    @commands.command(name="выйди", aliases=["leave", "выход"])
    async def leave(self, ctx):
        """🚪 Выгнать Пиздуна из войса"""
        vc = ctx.voice_client
        if vc and vc.is_connected():
            # Останавливаем дежурство если было
            await self._stop_duty(ctx.guild.id)
            # Останавливаем запись если активна
            if ctx.guild.id in self.bot.recordings:
                self.bot.recordings.pop(ctx.guild.id, None)
            if vc.is_listening():
                vc.stop_listening()
            await vc.disconnect()
            await ctx.send("**Пиздун:** Вас понял, отключаюсь. *шум статики* 🚪")
        else:
            await ctx.send("**Пиздун:** Я и так не в войсе, брат. Чего паникуешь?")

    # ===================== !слушай / !хватит =====================

    @commands.command(name="слушай", aliases=["listen", "rec"])
    async def start_listen(self, ctx, seconds: int = 30):
        """
        🎙️ Начать запись голоса в войсе
        Используется вместе с !хватит
        Записывает пока не скажешь !хватит (макс 60 секунд)
        """
        if seconds < 2 or seconds > 60:
            await ctx.send("**Пиздун:** Давай от 2 до 60 секунд, брат. Не гони.")
            return

        if ctx.guild.id in self.bot.recordings:
            await ctx.send(
                "**Пиздун:** Я уже записываю! Скажи `!хватит` сначала."
            )
            return

        try:
            vc = await self._ensure_voice(ctx)
        except commands.UserInputError:
            await ctx.send("**Пиздун:** Ты не в войсе, брат! Не починю.")
            return

        # Создаём RecordingSink
        sink = RecordingSink()

        # Стартуем прослушивание
        vc.listen(sink)

        # Запоминаем запись
        self.bot.recordings[ctx.guild.id] = {
            "sink": sink,
            "ctx": ctx,
            "vc": vc,
            "channel_id": ctx.channel.id,
        }

        # Таймер авто-остановки
        async def _timer():
            await asyncio.sleep(seconds)
            if ctx.guild.id in self.bot.recordings:
                rec = self.bot.recordings[ctx.guild.id]
                snk = rec.get("sink")
                user_count = len(snk._buffers) if snk else 0
                _log("REC", f"Таймер сработал | guild={ctx.guild.id} "
                     f"user={ctx.author.display_name} "
                     f"users_in_sink={user_count}")
                await ctx.send(
                    f"⏰ **Пиздун:** Запись остановлена. Напиши `!хватит` — "
                    f"может что-то и записалось."
                )

        self.bot.loop.create_task(_timer())

        _log("REC", f"Старт записи | guild={ctx.guild.id} "
             f"channel={ctx.author.voice.channel.name} "
             f"user={ctx.author.display_name} "
             f"max={seconds}s")

        await ctx.send(
            f"🎙️ **Пиздун:** Слышу тебя. Записываю (макс {seconds}с). "
            f"Скажи `!хватит` когда закончишь."
        )

    @commands.command(name="хватит", aliases=["stop", "recstop"])
    async def stop_listen(self, ctx):
        """⏹️ Остановить запись, распознать и ответить голосом"""
        rec = self.bot.recordings.pop(ctx.guild.id, None)

        if not rec:
            await ctx.send(
                "**Пиздун:** Я и так молчу, брат. Сначала скажи `!слушай`"
            )
            return

        sink = rec["sink"]
        vc = rec.get("vc") or ctx.voice_client

        await ctx.send("⏳ **Пиздун:** Обрабатываю...")

        # Останавливаем прослушивание
        if vc and vc.is_listening():
            vc.stop_listening()

        # Говорим синку что запись окончена
        sink.stop_recording()

        # Извлекаем аудио
        audio_data = sink.get_audio()

        if not audio_data:
            _log("REC", f"Пустой sink | guild={ctx.guild.id} | user={ctx.author.display_name}")
            await ctx.send(
                "**Пиздун:** Ничего не записалось. Может DAVE глушит? 🤔 "
                "Попробуй ещё раз или напиши текстом."
            )
            return

        # Берём первого пользователя кто говорил
        user_id, pcm_bytes = next(iter(audio_data.items()))
        audio_secs = len(pcm_bytes) / (48000 * 2 * 2)  # s16le stereo: 2 bytes × 2 channels
        _log("REC", f"PCM получен | user_id={user_id} "
             f"bytes={len(pcm_bytes)} ({audio_secs:.1f}s)")

        async with ctx.typing():
            t_start = time.time()

            # Распознаём речь через Transcriber
            text = await self._transcribe(pcm_bytes)

            t_elapsed = time.time() - t_start

            if not text:
                _log("REC", f"Транскрипция пуста | {len(pcm_bytes)} bytes "
                     f"({audio_secs:.1f}s) за {t_elapsed:.1f}s")
                await ctx.send(
                    "**Пиздун:** Ничего не разобрал. DAVE шифрует, "
                    "связь глушит. Попробуй ещё раз или напиши текстом. 🧱"
                )
                return

            _log("REC", f"Транскрипция ОК | {len(pcm_bytes)} bytes "
                 f"({audio_secs:.1f}s) за {t_elapsed:.1f}s | "
                 f"текст: {text[:100]}")

            # Отправляем в DeepSeek
            answer = await self._ask_deepseek(text, ctx.author.id)

            if ctx.author.id in self.bot.voice_only_users:
                # Только голос
                await self._say_in_voice(vc, answer)
            else:
                # Отправляем в чат и говорим в войс
                await ctx.send(
                    f"👤 **{ctx.author.display_name}:** {text}\n"
                    f"**Пиздун:** {answer}"
                )
                await self._say_in_voice(vc, answer)

    # ===================== !дежурь / !отдыхай =====================

    async def _enable_dave_passthrough(self, vc: discord.VoiceClient):
        """Включить DAVE passthrough для приёма аудио"""
        try:
            ds = vc._connection.dave_session
            if ds is not None and hasattr(ds, "set_passthrough_mode"):
                ds.set_passthrough_mode(True, 10)
                _log("DUTY", f"DAVE passthrough: ready={ds.ready} proto={ds.protocol_version}")
        except Exception as e:
            _log("DUTY", f"DAVE passthrough error: {e}")

    async def _handle_duty_utterance(self, member: discord.Member, pcm_bytes: bytes):
        """Обработка голосовой реплики в режиме дежурства"""
        guild_id = member.guild.id
        if guild_id not in self.bot.duty_guilds:
            return

        text = await self._transcribe(pcm_bytes)
        if not text:
            return

        text_lower = text.lower()
        wake_words = ["пиздун", "чедрик","кек"]
        hit = next((w for w in wake_words if w in text_lower), None)

        if hit is None:
            _log("DUTY", f"Пропущено (нет wake word): {member.display_name}: {text[:80]}")
            return

        _log("DUTY", f"🔥 Пробуждение! {member.display_name}: {text[:120]}")

        vc = member.guild.voice_client
        if not vc or not vc.is_connected():
            return

        # Пауза — бот будет говорить
        rec = self.bot.recordings.get(guild_id)
        if rec and rec.get("sink"):
            rec["sink"].paused = True

        # Убираем wake word из текста
        cleaned = text
        for w in wake_words:
            if w in cleaned.lower():
                idx = cleaned.lower().index(w)
                cleaned = cleaned[:idx] + cleaned[idx + len(w):]
        cleaned = cleaned.strip().strip(" ,.!?")
        if not cleaned:
            cleaned = text

        try:
            answer = await self._ask_deepseek(cleaned, member.id)
            _log("DUTY", f"Ответ: {answer[:100]}")
            await self._say_in_voice(vc, answer)
        except Exception as e:
            _log("ERROR", f"Duty AI: {e}")
        finally:
            if rec and rec.get("sink"):
                rec["sink"].paused = False
                _log("DUTY", "Прослушивание возобновлено")

    @commands.command(name="дежурь", aliases=["duty", "guard"])
    async def start_duty(self, ctx):
        """
        🛡️ Режим дежурства
        Пиздун сидит в войсе, слушает и отвечает голосом на слово «пиздун»
        """
        if ctx.guild.id in self.bot.duty_guilds:
            await ctx.send(
                "**Пиздун:** Я уже дежурю в этом канале! "
                "Скажи `!отдыхай` чтобы снять с дежурства."
            )
            return

        try:
            vc = await self._ensure_voice(ctx)
        except commands.UserInputError:
            await ctx.send("**Пиздун:** Ты не в войсе, брат! Не починю.")
            return

        # DAVE passthrough — расшифровка голоса
        await self._enable_dave_passthrough(vc)

        # Создаём событийный DutySink
        sink = DutySink(on_utterance=self._handle_duty_utterance)

        # Стартуем прослушивание
        vc.listen(sink)

        # Сохраняем состояние
        self.bot.duty_guilds.add(ctx.guild.id)
        self.bot.recordings[ctx.guild.id] = {
            "sink": sink,
            "ctx": ctx,
            "vc": vc,
        }

        _log("DUTY", f"Дежурство запущено | guild={ctx.guild.id} "
             f"channel={ctx.author.voice.channel.name}")

        await ctx.send(
            "🛡️ **Пиздун:** Заступил на дежурство! "
            "Жду слово **«пиздун»** в голосовом канале.\n"
            "Скажи `!отдыхай` чтобы снять с дежурства."
        )

    @commands.command(name="отдыхай", aliases=["rest", "unduty"])
    async def stop_duty(self, ctx):
        """🛡️ Снять Пиздуна с дежурства"""
        if ctx.guild.id not in self.bot.duty_guilds:
            await ctx.send(
                "**Пиздун:** Я и так отдыхаю, брат. Сначала скажи `!дежурь`."
            )
            return

        vc = ctx.voice_client

        # Останавливаем прослушивание
        if vc and vc.is_listening():
            vc.stop_listening()

        # Очищаем состояние
        await self._stop_duty(ctx.guild.id)
        if ctx.guild.id in self.bot.recordings:
            self.bot.recordings.pop(ctx.guild.id, None)

        _log("DUTY", f"Дежурство снято | guild={ctx.guild.id}")
        await ctx.send(
            "🛡️ **Пиздун:** Вас понял, снимаюсь с дежурства. Отдыхаю. 🧱"
        )

    async def _stop_duty(self, guild_id: int):
        """Остановить дежурство на гильдии"""
        self.bot.duty_guilds.discard(guild_id)
        task = self.duty_tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
