import json
import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

class TourneyConfigModal(Modal):
	def __init__(self, sql, *args, **kwargs):
		self.sql = sql
		super().__init__(*args, **kwargs)
		self.refToolInput = None
		self.add_item(InputText(label="Tourney Config", style=discord.InputTextStyle.long, required=False))
		self.add_item(InputText(label="Qualifier Config", style=discord.InputTextStyle.long, required=False))
		self.add_item(InputText(label="Bracket Config", style=discord.InputTextStyle.long, required=False))

	async def callback(self, interaction: discord.Interaction):
		#await interaction.defer(ephemeral=True)

		tourney = await self.sql.getActiveTournies(interaction.guild.id)
		if tourney == None:
			await interaction.response("No active tourney")

		for config in self.children:
			if config.label is "Tourney Config" and config.value != "":
				await self.sql.setTourneyConfig(tourney['id'], json.loads(config.value))

			if config.label is "Qualifier Config" and config.value != "":
				await self.sql.setTourneyQualifiers(tourney['id'], json.loads(config.value))

			if config.label is "Bracket Config" and config.value != "":
				await self.sql.setTourneyBrackets(tourney['id'], json.loads(config.value))		

		await interaction.response.send_message("Set whatever you sent me :shrug:")
		self.stop()

class OwnerCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	owner = discord.SlashCommandGroup('owner','Bot Owner Commands')

	@owner.command(name='tourneyconfig', description='Submit a tourney config/quali/bracket config for this server', integration_types={discord.IntegrationType.guild_install})
	@commands.is_owner()
	async def setTourney(self, ctx):
		modal = TourneyConfigModal(self.bot.tourneyDB, title="Mindful of the 4000 limit!")
		await ctx.send_modal(modal=modal)
		await modal.wait()

	@commands.Cog.listener()
	async def on_application_command_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
		if isinstance(error, commands.NotOwner):
			await ctx.respond("You don't own me! (You cannot run this command)", ephemeral=True)
		else:
			raise error

def setup(bot):
	bot.add_cog(OwnerCmds(bot))