"""
🧱 Пиздун 2.0 — Discord бот-компаньон
Переписано на discord.py + voice_recv (Rapptz master)
"""

import discord
from discord.ext import commands
from dotenv import load_dotenv
from prompt_manager import PromptManager
from tts_engine import TTSEngine
import os
import time
import asyncio


def log(tag: str, msg: str):
    """Форматированный лог с таймстемпом"""
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] [{tag}] {msg}")

# === Токен ===
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# === Настройки бота ===
intents = discord.Intents.default()
intents.message_content = True  # чтобы читал сообщения
intents.voice_states = True  # чтобы видел, кто в войсе

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    description="🧱 Пиздун — твой компаньон!",
)

# === Глобальное состояние (доступно из когов) ===
bot.voice_only_users: set[int] = set()  # кто включил режим «только голос»
bot.text_only_users: set[int] = set()  # кто включил режим «только текст» (без войса)
bot.duty_guilds: set[int] = set()  # какие гильдии в режиме дежурства
bot.recordings: dict[int, dict] = {}  # активные записи: {guild_id: {sink, ctx, channel_id}}

# === Менеджер промптов ===
bot.prompt_manager = PromptManager(prompts_dir="prompts")
bot.prompt_manager.default_prompt = "rail"
log("OK", f"Загружено промптов: {len(bot.prompt_manager.prompts)}")
log("", f"Дефолтный: {bot.prompt_manager.default_prompt}")

# === TTS движок ===
bot.tts_engine = TTSEngine()
engine_name = bot.tts_engine.active.capitalize()
log("OK", f"TTS движок: {engine_name} (по умолчанию)")


# ===== ЗАГРУЗКА КОГОВ =====

@bot.event
async def on_ready():
    """Бот зашёл на сервер — загружаем коги и говорим привет"""
    log("OK", f"Пиздун 2.0 в игре! Зашёл как {bot.user}")
    log("", f"ID: {bot.user.id}")
    log("", f"Серверов: {len(bot.guilds)}")

    # Статус бота
    await bot.change_presence(
        activity=discord.Game(name="Подпивасник | !хелп")
    )


# ===== ЛОГГЕР КОМАНД =====!

@bot.event
async def on_command(ctx):
    """Логировать каждый вызов команды"""
    args = ctx.kwargs if ctx.kwargs else {}
    args_str = f" {args}" if args else ""
    log("CMD", f"{ctx.author.display_name}: !{ctx.command.name}{args_str}")


@bot.event
async def on_command_completion(ctx):
    """Логировать успешное выполнение команды"""
    log("CMD", f"✓ !{ctx.command.name}")


@bot.event
async def on_command_error(ctx, error):
    """Логировать ошибки команд (кроме CommandNotFound — норм)"""
    if isinstance(error, discord.ext.commands.CommandNotFound):
        return  # Не засоряем лог неизвестными командами
    log("CMD", f"✗ !{ctx.command.name} — {error}")


@bot.event
async def on_message(message):
    """Читаем каждый чих в чате"""
    if message.author == bot.user:
        return

    # Если челика кто-то тегнул — отвечаем
    if bot.user in message.mentions:
        await message.reply("**Пиздун:** Чё надо? 🧱")

    # Пропускаем через команды
    await bot.process_commands(message)


# ===== ЗАПУСК =====
async def main():
    """Асинхронный запуск бота (load_extension теперь async в discord.py master)"""
    # Загружаем коги
    await bot.load_extension("cogs.misc_cog")
    await bot.load_extension("cogs.ai_cog")
    await bot.load_extension("cogs.voice_cog")
    await bot.load_extension("cogs.prompts_cog")
    log("OK", "Коги загружены!")

    if not TOKEN:
        log("ERROR", "Токен не найден! Добавь DISCORD_TOKEN=твой_токен в файл .env")
        return

    log("START", "Запускаем Пиздуна 2.0...")
    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
