"""
🎭 PromptsCog — команды для управления промптами
!промпты — список доступных
!промпт [имя] — сменить
"""

import discord
from discord.ext import commands


class PromptsCog(commands.Cog):
    """Управление персонажами-промптами Пиздуна"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="промпты")
    async def list_prompts(self, ctx):
        """📋 Показать список всех доступных промптов"""
        prompts = self.bot.prompt_manager.list_prompts()
        current = self.bot.prompt_manager.get_current_name(ctx.author.id)

        if not prompts:
            await ctx.send("**Пиздун:** Промпты не загружены, брат. Штаб пустой.")
            return

        lines = ["**📋 Доступные промпты:**"]
        for p in prompts:
            marker = "✅ **" if p["name"] == current else "• "
            lines.append(f"  {marker}`{p['name']}` — {p['description']}")

        lines.append(
            f"\n🎭 Текущий: **{current}**"
            f" ({self.bot.prompt_manager.get_current_description(ctx.author.id)})"
        )
        await ctx.send("\n".join(lines))

    @commands.command(name="промпт")
    async def set_prompt(self, ctx, name: str = None):
        """🎭 Сменить персонаж: !промпт [имя]

        Без аргумента — показывает текущий промпт.
        С именем — переключает.
        """
        if not name:
            current = self.bot.prompt_manager.get_current_name(ctx.author.id)
            desc = self.bot.prompt_manager.get_current_description(ctx.author.id)
            await ctx.send(
                f"**Пиздун:** Сейчас активен промпт «{current}» ({desc}).\n"
                f"Напиши `!промпт [имя]` чтобы сменить.\n"
                f"Список: `!промпты`"
            )
            return

        success, msg = self.bot.prompt_manager.set_prompt(ctx.author.id, name)
        if success:
            await ctx.send(f"**Пиздун:** ✅ {msg}")
        else:
            await ctx.send(f"**Пиздун:** ❌ {msg}")

    @commands.command(name="промпт-релоад")
    async def reload_prompts(self, ctx):
        """🔄 Перезагрузить все промпты из папки prompts/"""
        try:
            self.bot.prompt_manager.reload()
            count = len(self.bot.prompt_manager.prompts)
            current = self.bot.prompt_manager.get_current_name()
            await ctx.send(
                f"**Пиздун:** 🔄 Промпты перезагружены! Загружено: {count}.\n"
                f"Дефолтный: «{current}»"
            )
        except Exception as e:
            await ctx.send(
                f"**Пиздун:** ❌ Ошибка перезагрузки: {e}"
            )


async def setup(bot):
    await bot.add_cog(PromptsCog(bot))
