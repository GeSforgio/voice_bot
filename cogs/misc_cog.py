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
            color=0x00ff00,
        )
        embed.add_field(name="🧠 !чат [текст]", value="DeepSeek AI — текст + голос в войс (с историей)", inline=False)
        embed.add_field(name="🎤 !скажи [текст]", value="Сказать текст голосом в войсе", inline=False)
        embed.add_field(name="🎙️ !голос", value="`edge/silero` — движок | `список` — голоса | `voice [имя]` — выбрать", inline=False)
        embed.add_field(name="🎙️ !слушай [сек]", value="Запись голоса (2-60с), потом !хватит", inline=False)
        embed.add_field(name="⏹️ !хватит", value="Остановить запись → распознать → AI ответ", inline=False)
        embed.add_field(name="🛡️ !дежурь / !отдыхай", value="Слушает «пиздун» в войсе и отвечает / снять с дежурства", inline=False)
        embed.add_field(name="🚪 !выйди", value="Выгнать из войса", inline=False)
        embed.add_field(name="🔇 !молчи / 🔊 !говори", value="Только текст / вернуть голос", inline=False)
        embed.add_field(name="🤫 !тихо / 💬 !текст", value="Только голос / голос + текст", inline=False)
        embed.add_field(name="📝 !норм", value="`вкл/выкл` — норм-я текста | `mode neural|rule` — движок", inline=False)
        embed.add_field(name="🎭 !промпты / !промпт [имя]", value="Список персонажей / сменить / -релоад", inline=False)
        embed.add_field(name="!пиздун", value="Рандомная фраза", inline=False)
        embed.add_field(name="!автор", value="Кто создал", inline=False)
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

    # ===== НОРМАЛИЗАЦИЯ =====

    @commands.command(name="норм", aliases=["норматизация", "norm", "normalize"])
    async def norm_toggle(self, ctx, action: str = None, value: str = None):
        """📝 Управление нормализацией текста для TTS

        !норм — показать статус
        !норм вкл — включить нормализацию
        !норм выкл — отключить
        !норм mode neural — нейронная нормализация (RUNorm T5)
        !норм mode rule — rule-based (регексы, быстрее)
        """
        uid = ctx.author.id

        if not action:
            status = "✅ вкл" if uid not in self.bot.normalization_disabled else "❌ выкл"
            mode = self.bot.normalizer.mode
            await ctx.send(
                f"**📝 Нормализация текста:** {status}\n"
                f"   Режим: {mode}\n"
                f"   Помогает TTS правильно читать числа, валюты, "
                f"телефоны и аббревиатуры.\n"
                f"   `!норм вкл` / `!норм выкл` / `!норм mode neural|rule`"
            )
            return

        if action == "mode":
            if not value:
                await ctx.send(f"**📝 Пиздун:** Режим: `{self.bot.normalizer.mode}`. Смени через `!норм mode neural` или `!норм mode rule`")
                return
            msg = self.bot.normalizer.set_mode(value)
            await ctx.send(f"**📝 Пиздун:** {msg}")
            return

        if action in ("выкл", "off", "disable", "0"):
            self.bot.normalization_disabled.add(uid)
            await ctx.send(
                "**📝 Пиздун:** Отключаю нормализацию. Буду читать как есть. "
                "Цифры побуквенно, валюты сырыми. 😤"
            )
            return

        if action in ("вкл", "on", "enable", "1"):
            self.bot.normalization_disabled.discard(uid)
            await ctx.send(
                "**📝 Пиздун:** Включаю нормализацию! "
                "«150 рублей» вместо «один пять ноль руб плюс». Красота. ✅"
            )
            return

        await ctx.send("**Пиздун:** Не понял. Пиши `!норм вкл` / `!норм выкл` / `!норм mode neural|rule`")


async def setup(bot):
    await bot.add_cog(MiscCog(bot))
