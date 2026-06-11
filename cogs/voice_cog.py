"""
🎤 VoiceCog — голосовые команды Пиздуна
!скажи, !выйди, !слушай, !хватит, !дежурь, !отдыхай

ВАЖНО: Voice RECEIVE (запись голоса) может не работать из-за
DAVE (End-to-End Encryption) от Discord. Это баг PyCord 2.8.0.
Следим за: https://github.com/Pycord-Development/pycord/issues/3139
"""

import discord
from discord.ext import commands
from discord.sinks import WaveSink, Sink
import asyncio
import os
import tempfile
import wave
import io
from faster_whisper import WhisperModel
from openai import OpenAI
import ai_config
import logging

# Monkey-patch для бага PyCord 2.8.0:
# Sink не имеет __sink_listeners__, но SinkEventRouter их ищет
if not hasattr(Sink, "__sink_listeners__"):
    Sink.__sink_listeners__ = []
    Sink.walk_children = lambda self: []

# PyCord 2.8.0 PacketDecoder вызывает sink.is_opus() — добавляем
if not hasattr(Sink, "is_opus"):
    Sink.is_opus = lambda self: False
if not hasattr(Sink, "wants_opus"):
    Sink.wants_opus = lambda self: False

# PyCord 2.8.0: Router передаёт VoiceData в Sink.write(), но Sink ждёт bytes
# Чиним: извлекаем pcm из VoiceData
from discord.voice import VoiceData as _VoiceData

_original_sink_write = Sink.write

def _patched_sink_write(self, data, user):
    # VoiceData → bytes (pcm)
    if isinstance(data, _VoiceData):
        data = data.pcm or b""
    return _original_sink_write(self, data, user)

Sink.write = _patched_sink_write
print("[PATCH] Sink.write — VoiceData → PCM bytes")

# Monkey-patch для DAVE: логируем ошибки расшифровки, не глушим пакеты
import discord.voice.receive.reader as reader_mod
import davey

_original_decrypt_rtp = reader_mod.PacketDecryptor.decrypt_rtp

def _patched_decrypt_rtp(self, packet):
    state = self.client._connection
    dave = state.dave_session

    raw_payload = self._decryptor_rtp(packet)

    if dave is not None and dave.ready:
        uid = state.ssrc_user_map.get(packet.ssrc)
        if uid:
            try:
                decrypted_audio = dave.decrypt(
                    uid,
                    davey.MediaType.audio,
                    raw_payload,
                )
                if packet.extended:
                    offset = packet.update_extended_header(decrypted_audio)
                    packet.decrypted_data = decrypted_audio[offset:]
                else:
                    packet.decrypted_data = decrypted_audio
                return packet.decrypted_data
            except Exception as exc:
                print(f"[DAVE] Пропущен пакет (ssrc={packet.ssrc}): {type(exc).__name__}: {exc}")
                packet.decrypted_data = None
                return None

    # DAVE не готов — пакет пропускаем (данные ещё зашифрованы)
    packet.decrypted_data = None
    return None

reader_mod.PacketDecryptor.decrypt_rtp = _patched_decrypt_rtp
print("[PATCH] decrypt_rtp — DAVE ошибки не глушат аудио")

# Константы аудио (из PyCord Decoder)
SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2  # 16-bit

# Глобальный whisper (грузится один раз)
_whisper: WhisperModel | None = None


def get_whisper() -> WhisperModel:
    """Ленивая загрузка Whisper (один раз при первом вызове)"""
    global _whisper
    if _whisper is None:
        print("[WHISPER] Загружаю Whisper (base)...")
        _whisper = WhisperModel("base", device="cpu", compute_type="int8")
        print("[WHISPER] OK!")
    return _whisper


class VoiceCog(commands.Cog):
    """Голосовые команды Пиздуна"""

    def __init__(self, bot):
        self.bot = bot
        self.ai_client = OpenAI(
            api_key=ai_config.AI_API_KEY,
            base_url=ai_config.AI_ENDPOINT,
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
                # Включаем DAVE passthrough
                try:
                    ds = vc._connection.dave_session
                    if ds is not None and hasattr(ds, 'set_passthrough_mode'):
                        ds.set_passthrough_mode(True, 10)
                except:
                    pass
            return vc

        vc = await ctx.author.voice.channel.connect()

        # Включить DAVE passthrough и диагностику
        try:
            logging.getLogger('discord.voice').setLevel(logging.DEBUG)

            ds = vc._connection.dave_session
            if ds is not None and hasattr(ds, 'set_passthrough_mode'):
                ds.set_passthrough_mode(True, 10)
                print(f"[DAVE] Passthrough ON | ready={ds.ready} | proto={ds.protocol_version}")
                print(f"[DAVE] status={ds.status} | epoch={ds.epoch}")
        except Exception as e:
            print(f"[DAVE] Ошибка: {e}")

        return vc

    @staticmethod
    def _pcm_to_wav(raw_data: bytes) -> bytes:
        """Добавить WAV-заголовок к сырым PCM данным"""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(raw_data)
        buf.seek(0)
        return buf.read()

    @staticmethod
    def _get_sink_data(sink: WaveSink) -> dict[int, bytes]:
        """
        Извлечь WAV-данные из синка после записи.
        Так как cleanup() не вызывается автоматически в pycord 2.8.0,
        форматируем WAV вручную.
        """
        result = {}
        for user_id, audio_data in sink.audio_data.items():
            raw = audio_data.file.read()
            if raw:
                wav_bytes = VoiceCog._pcm_to_wav(raw)
                result[user_id] = wav_bytes
        return result

    async def _transcribe(self, wav_bytes: bytes) -> str | None:
        """Распознать речь через faster-whisper"""
        whisper = get_whisper()
        try:
            # faster-whisper умеет читать из файла, сохраняем во временный
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp_path = f.name

            segments, _ = whisper.transcribe(tmp_path, language="ru")
            text = " ".join(seg.text for seg in segments).strip()
            os.unlink(tmp_path)
            return text if text else None
        except Exception as e:
            print(f"[ERROR] Whisper: {e}")
            return None

    async def _ask_deepseek(self, text: str, user_id: int = None) -> str:
        """Отправить текст в DeepSeek и получить ответ"""
        response = self.ai_client.chat.completions.create(
            model=ai_config.AI_MODEL,
            messages=[
                {"role": "system", "content": self.bot.prompt_manager.get_prompt(user_id)},
                {"role": "user", "content": text},
            ],
            max_tokens=512,
            temperature=0.7,
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
            print(f"[ERROR] TTS: {e}")

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

        # Ждём DAVE сессию (если она есть — даём время на handshake)
        ds = vc._connection.dave_session
        if ds is not None:
            for i in range(100):  # до 5 секунд
                if ds.ready:
                    print(f"[DAVE] Session ready after {i*0.1:.1f}s | epoch={ds.epoch} | status={ds.status}")
                    # Включаем passthrough когда сессия уже активна
                    ds.set_passthrough_mode(True, 10)
                    print(f"[DAVE] Passthrough mode установлен")
                    break
                await asyncio.sleep(0.1)
            else:
                print(f"[DAVE] Session NOT ready after 5s — DAVE не активен?")
                # Всё равно пробуем — может DAVE не используется
        # Создаём WaveSink с таймером (авто-стоп если забыли сказать !хватит)
        sink = WaveSink(filters={"time": seconds})

        # Ссылка на синк — запишем результат когда таймер сработает
        self.bot.recordings[ctx.guild.id] = {
            "sink": sink,
            "ctx": ctx,
            "vc": vc,
            "channel_id": ctx.channel.id,
        }

        # Колбэк на случай если таймер сработал раньше !хватит
        async def _on_timer_stop(exception):
            """Вызывается когда запись остановлена"""
            if ctx.guild.id not in self.bot.recordings:
                return

            if exception:
                import traceback
                tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
                print(f"[DAVE] Запись прервана ошибкой:\n{tb[:1000]}")
                self.bot.recordings[ctx.guild.id]["dave_error"] = str(exception)
            else:
                print("[DAVE] Запись остановлена по таймеру")

            await ctx.send(
                f"⏰ **Пиздун:** Запись остановлена. Напиши `!хватит` — "
                f"может что-то и записалось."
            )

        def _callback(exception):
            """Синхронный колбэк — запускает асинхронный через loop"""
            asyncio.run_coroutine_threadsafe(_on_timer_stop(exception), self.bot.loop)

        # Стартуем запись с колбэком
        # PyCord 2.8.0 баг: sink.client не инициализирован — чиним вручную
        sink.init(vc)
        vc.start_recording(sink, _callback)

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

        # Останавливаем запись если ещё активна
        if vc and vc.is_recording():
            try:
                vc.stop_recording()
            except Exception as e:
                print(f"[WARN] stop_recording: {e}")

        # Извлекаем аудио из синка
        audio_data = self._get_sink_data(sink)

        if not audio_data:
            await ctx.send(
                "**Пиздун:** Ничего не записалось. Может DAVE глушит? 🤔 "
                "Попробуй ещё раз или напиши текстом."
            )
            return

        # Берём первого пользователя кто говорил
        wav_bytes = list(audio_data.values())[0]

        async with ctx.typing():
            # Распознаём речь
            text = await self._transcribe(wav_bytes)

            if not text:
                await ctx.send(
                    "**Пиздун:** Ничего не разобрал. DAVE шифрует, "
                    "связь глушит. Попробуй ещё раз или напиши текстом. 🧱"
                )
                return

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

    @commands.command(name="дежурь", aliases=["duty", "guard"])
    async def start_duty(self, ctx):
        """
        🛡️ Режим дежурства
        ⛔ НЕ РАБОТАЕТ — DAVE-шифрование ломает приём голоса
        """
        await ctx.send(
            "🚫 **Пиздун:** Дежурство не работает — DAVE глушит приём. "
            "Но я могу сидеть в войсе и отвечать текстом: `!чат [вопрос]`"
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

    async def _duty_loop(
        self, guild_id: int, voice_channel: discord.VoiceChannel, ctx: commands.Context
    ):
        """
        Фоновая задача дежурства.
        Записывает чанки по 5 секунд, проверяет есть ли слово «Пиздун».
        """
        vc = voice_channel.guild.voice_client

        while guild_id in self.bot.duty_guilds and vc and vc.is_connected():
            # Записываем чанк
            chunk_done = asyncio.Event()
            sink = WaveSink(filters={"time": 5})

            # Колбэк вызывается из другого потока (Filters.wait_and_stop)
            def _on_chunk_done(exc):
                self.bot.loop.call_soon_threadsafe(chunk_done.set)

            try:
                vc.start_recording(sink, _on_chunk_done)
                # Ждём окончания записи (таймер 5 секунд)
                await asyncio.wait_for(chunk_done.wait(), timeout=8)
            except (asyncio.TimeoutError, Exception) as e:
                print(f"[WARN] Ошибка в цикле дежурства: {e}")
                if vc.is_recording():
                    vc.stop_recording()
                await asyncio.sleep(1)
                continue

            # Извлекаем и распознаём аудио
            audio_data = self._get_sink_data(sink)
            if not audio_data:
                await asyncio.sleep(0.5)
                continue

            wav_bytes = list(audio_data.values())[0]
            text = await self._transcribe(wav_bytes)

            if text and "пиздун" in text.lower():
                # Проснулись! Отвечаем
                print(f"[WAKE] Пиздун проснулся! Сказали: {text[:100]}")
                answer = await self._ask_deepseek(text)

                try:
                    await self._say_in_voice(vc, answer)
                except Exception as e:
                    print(f"[ERROR] TTS в дежурстве: {e}")

            # Небольшая пауза перед следующим чанком
            await asyncio.sleep(0.5)

    @commands.command(name="отдыхай", aliases=["offduty", "standdown"])
    async def stop_duty(self, ctx):
        """🍺 Снять Пиздуна с дежурства"""
        if ctx.guild.id not in self.bot.duty_guilds:
            await ctx.send("**Пиздун:** Я и так отдыхаю, пиво пью. 🍺")
            return

        await self._stop_duty(ctx.guild.id)
        await ctx.send("**Пиздун:** Отбой, брат. Смену сдал. Иду пить пиво. 🍺")


def setup(bot):
    bot.add_cog(VoiceCog(bot))
