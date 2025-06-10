@bot.slash_command(name="test",Description="Fellow Bar")
async def test(ctx: discord.ApplicationContext):
    await ctx.respond("This works maybe?")
