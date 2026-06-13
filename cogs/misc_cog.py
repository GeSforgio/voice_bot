"""
🧱 MiscCog — базовые команды Пиздуна
!хелп, !пиздун, !автор, !тихо, !текст, !отдыхай
"""

import discord
from discord.ext import commands
import random


class MiscCog(commands.Cog):
    """Базовые команды для Пиздуна"""

    def __init__(self, bot):
        self.bot = bot

    # ===== ХЕЛП =====

    @commands.command(name="хелп", aliases=["команды"])
    async def cmds(self, ctx):
        """Показать все команды"""
        embed = discord.Embed(
            title="🧱 Пиздун — Команды",
            description="Чё я умею, короче:",
            color=0x00ff00,  # майнкрафт-зелёный
        )
        embed.add_field(name="!хелп", value="Это вот сюда ты щас написал", inline=False)
        embed.add_field(name="!пиздун", value="Пиздун что-то скажет", inline=False)
        embed.add_field(name="!автор", value="Кто меня создал", inline=False)
        embed.add_field(name="🧠 !чат [текст]", value="DeepSeek — отвечает текстом + голосом в войс", inline=False)
        embed.add_field(
            name="🎤 !скажи [текст]", value="Сказать текст голосом в войсе", inline=False
        )
        embed.add_field(
            name="🎙️ !голос",
            value=(
                "Управление TTS:\n"
                "`!голос` — статус\n"
                "`!голос edge/silero` — движок\n"
                "`!голос список` — голоса\n"
                "`!голос voice [имя]` — выбрать"
            ),
            inline=False,
        )
        embed.add_field(
            name="🎙️ !слушай [сек]",
            value="Запись голоса (потом !хватит)",
            inline=False,
        )
        embed.add_field(name="⏹️ !хватит", value="Остановить и распознать", inline=False)
        embed.add_field(
            name="🛡️ !дежурь",
            value="Жду слово «пиздун» в войсе и отвечаю",
            inline=False,
        )
        embed.add_field(name="🚪 !выйди", value="Выгнать из войса", inline=False)
        embed.add_field(name="🤫 !тихо / !войс", value="Только голос, без текста", inline=False)
        embed.add_field(name="💬 !текст / !дублируй", value="Голос + текст в чат", inline=False)
        embed.add_field(name="🔇 !молчи / !mute", value="Только текст, без войса", inline=False)
        embed.add_field(name="🔊 !говори", value="Вернуть голос в эфир", inline=False)
        embed.add_field(
            name="🎭 !промпты / !промпт",
            value="Список персонажей / сменить",
            inline=False,
        )
        embed.set_footer(text="Работает на Пиве ⚡")

        await ctx.send(embed=embed)

    # ===== ПИЗДУН =====

    @commands.command(name="пиздун", aliases=["пидор", "чедрик"])
    async def cheedrik_says(self, ctx, *, text=None):
        """Пиздун отвечает"""
        if text:
            await ctx.send(
                f"**Пиздун:** *ковыряется в носу* «{text}»... ну такое, брат 🤷"
            )
        else:
            answers = [
                "*звук поршня* Чё?!",
                "*ест хлеб* Ну чё там?",
                "🧱... видел мою постройку?",
                "*клацает редстоуном* Занят я, погоди",
                "Зачем позвал? Дрочить криперов иду",
            ]
            await ctx.send(f"**Пиздун:** {random.choice(answers)}")

    # ===== АВТОР =====

    @commands.command(name="автор", aliases=["кто", "creator"])
    async def author(self, ctx):
        """Кто создал этого красавчика"""
        await ctx.send("**Пиздун:** Меня забацал **Кирилл** (KirillLOL). Красавчик, да? 🫡")

    # ===== РЕЖИМЫ =====

    @commands.command(name="тихо", aliases=["vo","войс"])
    async def voice_only(self, ctx):
        """🤫 Пиздун говорит только в войсе, в чат не пишет"""
        self.bot.voice_only_users.add(ctx.author.id)
        self.bot.text_only_users.discard(ctx.author.id)
        await ctx.send("**Пиздун:** Приём. Работаю по голосу. В эфир не выхожу. 🎤")

    @commands.command(name="текст", aliases=["text", "дублируй"])
    async def text_mode(self, ctx):
        """💬 Пиздун пишет в чат + говорит в войс"""
        self.bot.voice_only_users.discard(ctx.author.id)
        self.bot.text_only_users.discard(ctx.author.id)
        await ctx.send("**Пиздун:** Вас понял. Возвращаюсь в текстовый режим. 📝")

    @commands.command(name="молчи", aliases=["mute", "nosound"])
    async def text_only(self, ctx):
        """🔇 Пиздун отвечает только текстом, без голоса в войс"""
        self.bot.text_only_users.add(ctx.author.id)
        self.bot.voice_only_users.discard(ctx.author.id)
        await ctx.send("**Пиздун:** Принял. Работаю только текстом, молчу в эфире. 🔇")

    @commands.command(name="говори", aliases=["unsound"])
    async def unmute_voice(self, ctx):
        """🔊 Пиздун снова говорит голосом"""
        self.bot.text_only_users.discard(ctx.author.id)
        await ctx.send("**Пиздун:** Вас понял. Возвращаю голос в эфир. 🔊")

async def setup(bot):
    await bot.add_cog(MiscCog(bot))
