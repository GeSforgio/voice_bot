"""
🧠 AICog — команды AI-чата
!чат [текст] — общение с DeepSeek через PUBG-промпт
Отвечает текстом + голосом в войс если ты в канале
"""

import discord
from discord.ext import commands
from openai import OpenAI
import ai_config
import os
import asyncio

# Максимум сообщений в истории диалога на пользователя
MAX_HISTORY = 20


class AICog(commands.Cog):
    """AI-чат с DeepSeek через промпт солдата PUBG"""

    def __init__(self, bot):
        self.bot = bot
        self.ai_client = OpenAI(
            api_key=ai_config.AI_API_KEY,
            base_url=ai_config.AI_ENDPOINT,
        )
        # История диалогов: {user_id: [{"role": "user"/"assistant", "content": "..."}]}
        self.history: dict[int, list[dict]] = {}

    def get_history(self, user_id: int) -> list[dict]:
        """Получить или создать историю диалога для пользователя"""
        if user_id not in self.history:
            self.history[user_id] = []
        return self.history[user_id]

    async def _say_in_voice(self, ctx, text: str):
        """Сказать текст в войс-канал пользователя (если он в канале)"""
        if not ctx.author.voice:
            return False

        vc = ctx.voice_client
        try:
            if vc and vc.is_connected():
                if vc.channel.id != ctx.author.voice.channel.id:
                    await vc.move_to(ctx.author.voice.channel)
            else:
                vc = await ctx.author.voice.channel.connect()
        except Exception as e:
            print(f"[TTS] Не смог подключиться к войсу: {e}")
            return False

        # Генерируем TTS и проигрываем
        try:
            tmp_path, _ = await self.bot.tts_engine.speak(text)

            while vc.is_playing():
                await asyncio.sleep(0.5)

            vc.play(
                discord.FFmpegPCMAudio(tmp_path),
                after=lambda e: os.unlink(tmp_path) if os.path.exists(tmp_path) else None,
            )
            return True
        except Exception as e:
            print(f"[TTS] Ошибка воспроизведения: {e}")
            return False

    # ===== !чат =====

    @commands.command(name="чат", aliases=["ask", "question"])
    async def chat(self, ctx, *, question: str = None):
        """🧠 Спросить у DeepSeek — ответит текстом и голосом если ты в войсе"""
        if not question:
            await ctx.send(
                "**Пиздун:** Чё спросить-то хотел? Напиши `!чат [вопрос]`"
            )
            return

        # Показываем "бот печатает"
        async with ctx.typing():
            history = self.get_history(ctx.author.id)

            # Собираем сообщения: системный промпт + последние N из истории + новый вопрос
            messages = [
                {"role": "system", "content": self.bot.prompt_manager.get_prompt(ctx.author.id)},
                *history[-MAX_HISTORY:],
                {"role": "user", "content": question},
            ]

            try:
                response = self.ai_client.chat.completions.create(
                    model=ai_config.AI_MODEL,
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.7,
                )

                answer = response.choices[0].message.content

                # Сохраняем в историю
                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": answer})

                # Отправляем текст в чат (если не voice-only режим)
                if ctx.author.id not in self.bot.voice_only_users:
                    text_answer = answer
                    if len(text_answer) > 1900:
                        text_answer = text_answer[:1900] + "...\n\n*✅ ответ обрезан, был длиннее*"
                    await ctx.send(f"**Пиздун:** {text_answer}")

                # Всегда пробуем сказать голосом если пользователь в войсе
                voice_ok = await self._say_in_voice(ctx, answer)

            except Exception as e:
                error_msg = str(e)[:150]
                await ctx.send(
                    f"**Пиздун:** Ошибка связи, брат. Штаб не отвечает. "
                    f"Рация фонит: `{error_msg}`"
                )


def setup(bot):
    bot.add_cog(AICog(bot))
