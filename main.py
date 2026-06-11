"""
🧱 Пиздун 2.0 — Discord бот-компаньон
Переписано на PyCord 2.8.0 с когами
"""

import discord
from discord.ext import commands
from dotenv import load_dotenv
from prompt_manager import PromptManager
from tts_engine import TTSEngine
import os

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
bot.duty_guilds: set[int] = set()  # какие гильдии в режиме дежурства
bot.recordings: dict[int, dict] = {}  # активные записи: {guild_id: {sink, ctx, channel_id}}

# === Менеджер промптов ===
bot.prompt_manager = PromptManager(prompts_dir="prompts")
bot.prompt_manager.default_prompt = "rail"
print(f"[OK] Загружено промптов: {len(bot.prompt_manager.prompts)}")
print(f"     Дефолтный: {bot.prompt_manager.default_prompt}")

# === TTS движок ===
bot.tts_engine = TTSEngine()
print(f"[OK] TTS движок: Edge TTS (по умолчанию)")


# ===== ЗАГРУЗКА КОГОВ =====

@bot.event
async def on_ready():
    """Бот зашёл на сервер — загружаем коги и говорим привет"""
    print(f"[OK] Пиздун 2.0 в игре! Зашёл как {bot.user}")
    print(f"     ID: {bot.user.id}")
    print(f"     Серверов: {len(bot.guilds)}")

    # Статус бота
    await bot.change_presence(
        activity=discord.Game(name="Подпивасник | !хелп")
    )


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
if __name__ == "__main__":
    # Загружаем коги
    bot.load_extension("cogs.misc_cog")
    bot.load_extension("cogs.ai_cog")
    bot.load_extension("cogs.voice_cog")
    bot.load_extension("cogs.prompts_cog")
    print("[OK] Коги загружены!")

    if not TOKEN:
        print("[ERROR] Токен не найден!")
        print("   Добавь DISCORD_TOKEN=твой_токен в файл .env")
        exit(1)

    print("[START] Запускаем Пиздуна 2.0...")
    bot.run(TOKEN)
