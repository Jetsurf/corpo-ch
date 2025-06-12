import discord, requests
from discord.ext import commands

class fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # api urls
        self.no.url = 'https://naas.isalman.dev/no'
        self.joke.url = 'https://icanhazdadjoke.com/'
    
    fun = discord.SlashCommandGroup('fun','Fun stuff!')

    @fun.command(name='no',description='Just say no')
    async def no(self, ctx):
        resp = requests.get(self.no.url)
        await ctx.respond(resp.json()['reason'])

    @fun.command(name='joke',description='Need a joke? Have a joke!')
    async def joke(self, ctx):
        resp = requests.get(self.joke.url,headers={"Accept":"application/json"})
        await ctx.respond(resp.json()['joke'])

def setup(bot):
    bot.add_cog(fun(bot))
