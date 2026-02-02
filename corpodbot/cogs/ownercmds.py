import json
import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

from corpoch.models import Tournament, TournamentBracket, TournamentPlayer, TournamentQualifier

## These Were obsoleted by django admin - keeping for discord end specific commands

class OwnerCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	owner = discord.SlashCommandGroup('owner','Bot Owner Commands')

def setup(bot):
	bot.add_cog(OwnerCmds(bot))