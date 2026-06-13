"""
🧠 AICog — команды AI-чата
!чат [текст] — общение с DeepSeek через PUBG-промпт
Отвечает текстом + голосом в войс если ты в канале
"""

import discord
from discord.ext import commands
import ai_config
import os
import asyncio
import time
from discord.ext import voice_recv
from cogs.llm_client import create_llm
from cogs.llm_tools import TOOLS

# Максимум сообщений в истории диалога на пользователя
MAX_HISTORY = 20


def _log(tag: str, msg: str):
    """Лог с таймстемпом"""
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] [{tag}] {msg}")


def strip_markdown(text: str) -> str:
    """Удалить markdown-разметку для TTS (чтобы не читал звёздочки и тэги)"""
    import re
    # **жирный** → жирный
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # *курсив* → курсив
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # __подчёркнутый__ → подчёркнутый
    text = re.sub(r'__(.+?)__', r'\1', text)
    # `код` → код
    text = re.sub(r'`(.+?)`', r'\1', text)
    # [текст](ссылка) → текст
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    # # заголовки → убрать #
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    # > цитаты → убрать >
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    return text.strip()


class AICog(commands.Cog):
    """AI-чат с DeepSeek через LangChain с тулзами"""

    def __init__(self, bot):
        self.bot = bot
        self.llm = create_llm(max_tokens=ai_config.AI_MAX_TOKENS_CHAT)
        self.llm_with_tools = self.llm.bind_tools(TOOLS)
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
                vc = await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
        except Exception as e:
            print(f"[TTS] Не смог подключиться к войсу: {e}")
            return False

        # Генерируем TTS и проигрываем
        try:
            clean_text = strip_markdown(text)
            tmp_path, _ = await self.bot.tts_engine.speak(clean_text)

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
            base_prompt = self.bot.prompt_manager.get_prompt(ctx.author.id)

            # Промпт с описанием тулзов — только для раунда вызова инструментов
            tool_prompt = base_prompt + (
                "\n\nДоступные инструменты:"
                "\n- web_search — поиск в интернете (новости, ссылки, факты)"
                "\n- read_url — чтение содержимого сайта по URL"
                "\nЕсли вопрос подразумевает поиск информации — используй web_search."
                "\nЕсли пользователь просит зайти на конкретный сайт — используй read_url."
                "\n\nВАЖНО: Когда тебе вернулись результаты из web_search или read_url — "
                "ОТВЕЧАЙ ИСКЛЮЧИТЕЛЬНО НА ОСНОВЕ ЭТИХ ДАННЫХ. "
                "Не выдумывай и не используй свои старые знания. "
                "Результаты поиска — это единственный источник правды."
            )
            # Чистый промпт без упоминания инструментов — для финального ответа
            clean_prompt = base_prompt + (
                "\n\nЕсли тебе вернулись результаты поиска — "
                "отвечай на основе этих данных. Не выдумывай."
            )

            messages = [
                {"role": "system", "content": tool_prompt},
                *history[-MAX_HISTORY:],
                {"role": "user", "content": question},
            ]

            try:
                MAX_TOOL_ROUNDS = 1
                tool_rounds = 0

                response = await self.llm_with_tools.ainvoke(messages)

                # Многораундовый tool calling: DeepSeek может вызывать тулзы несколько раз
                while (
                    hasattr(response, "tool_calls")
                    and response.tool_calls
                    and tool_rounds < MAX_TOOL_ROUNDS
                ):
                    tool_rounds += 1
                    _log("TOOL", f"Раунд {tool_rounds}: {len(response.tool_calls)} тул(ов)")
                    messages.append(response.model_dump())

                    any_called = False
                    for tc in response.tool_calls:
                        _log("TOOL", f"→ {tc['name']}({tc['args']})")
                        tool_fn = next((t for t in TOOLS if t.name == tc["name"]), None)
                        if tool_fn:
                            result = tool_fn.invoke(tc["args"])
                            _log("TOOL", f"← результат ({len(str(result))} символов)")
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": str(result),
                            })
                            any_called = True

                    if not any_called:
                        break

                    # Проверяем качество последнего результата тулза
                    last_tool = None
                    for msg in reversed(messages):
                        if msg.get("role") == "tool":
                            last_tool = msg
                            break
                    if last_tool:
                        content = last_tool.get("content", "")
                        good = (
                            len(content) > 200
                            and "ничего не найдено" not in content.lower()
                            and "ошибка" not in content.lower()
                        )
                        if good:
                            _log("TOOL", "Результат хороший, дополнительный раунд не нужен")
                            break

                    # Снова с тулзами — DeepSeek может решить вызвать read_url как фолбэк
                    response = await self.llm_with_tools.ainvoke(messages)

                # Финальный проход
                if tool_rounds > 0:
                    _log("TOOL", f"Финальный ответ после {tool_rounds} раунд(ов) тулзов...")
                    # Убираем из системного промпта упоминания инструментов — тулзов больше нет
                    messages[0] = {"role": "system", "content": clean_prompt}
                    final = await self.llm.ainvoke(messages)
                    answer = final.content
                else:
                    answer = response.content

                # Сохраняем в историю
                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": answer})

                # Отправляем текст в чат
                if ctx.author.id not in self.bot.voice_only_users:
                    text_answer = answer
                    if len(text_answer) > 1900:
                        text_answer = text_answer[:1900] + "...\n\n*✅ ответ обрезан, был длиннее*"
                    await ctx.send(f"**Пиздун:** {text_answer}")

                # Пробуем сказать голосом
                voice_ok = False
                if ctx.author.id not in self.bot.text_only_users:
                    voice_ok = await self._say_in_voice(ctx, answer)

            except Exception as e:
                error_msg = str(e)[:150]
                await ctx.send(
                    f"**Пиздун:** Ошибка связи, брат. Штаб не отвечает. "
                    f"Рация фонит: `{error_msg}`"
                )


async def setup(bot):
    await bot.add_cog(AICog(bot))
