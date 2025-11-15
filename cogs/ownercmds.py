import json
import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

class TourneyConfigModal(Modal):
	def __init__(self, sql, *args, **kwargs):
		self.sql = sql
		super().__init__(*args, **kwargs)
		self.add_item(InputText(label="Tourney Config", style=discord.InputTextStyle.long, required=False))
		self.add_item(InputText(label="Qualifier Config", style=discord.InputTextStyle.long, required=False))
		self.add_item(InputText(label="Bracket Config", style=discord.InputTextStyle.long, required=False))

	async def callback(self, interaction: discord.Interaction):
		tourney = await self.sql.getActiveTournies(interaction.guild.id)
		if tourney == None:
			await interaction.respond("No active tourney")

		try:
			for config in self.children:
				if config.label == "Tourney Config" and config.value != "":
					await self.sql.setTourneyConfig(tourney['id'], json.loads(config.value))
				if config.label == "Qualifier Config" and config.value != "":
					await self.sql.setTourneyQualifiers(tourney['id'], json.loads(config.value))
				if config.label == "Bracket Config" and config.value != "":
					await self.sql.setTourneyBrackets(tourney['id'], json.loads(config.value))		
		except Exception as e:
			await interaction.respond(f"Failed to set config: {e}", ephemeral=True)
			self.stop()
			return

		await interaction.respond("Successfully set whatever you sent me :shrug:", ephemeral=True, delete_after=5)
		self.stop()

class TourneyMatchInProcessModal(Modal):
	def __init__(self, sql, *args, **kwargs):
		self.sql = sql
		super().__init__(*args, **kwargs)
		self.add_item(InputText(label="TourneyID", style=discord.InputTextStyle.short, max_length=4, required=True))
		self.add_item(InputText(label="Finished", style=discord.InputTextStyle.short, max_length=1, required=True, value=1))
		self.add_item(InputText(label="Match/Reftool JSON", style=discord.InputTextStyle.long, required=True))
		self.callback = self.callback

	async def callback(self, interaction: discord.Interaction):
		tourney = await self.sql.getActiveTournies(interaction.guild.id)
		if tourney == None:
			await interaction.followup.send("No active tourney")

		#Get UUID from Json rather than separate modal field
		data = json.loads(self.children[2].value)
		await self.sql.replaceRefToolMatch(data['uuid'], int(self.children[0].value), bool(self.children[1].value), json.loads(self.children[2].value))

		await interaction.respond("Successfully set whatever you sent me :shrug:", ephemeral=True, delete_after=5)
		self.stop()

class PlayerModal(Modal):
	def __init__(self, sql, *args, **kwargs):
		self.sql = sql
		super().__init__(*args, **kwargs)
		self.add_item(InputText(label="Player ID", style=discord.InputTextStyle.short, max_length=4, required=True))
		self.add_item(InputText(label="CH Name", style=discord.InputTextStyle.short, max_length=1, required=False))
		self.add_item(InputText(label="Is Active", style=discord.InputTextStyle.short, max_length=1, required=False, placeholder="1/0"))
		self.add_item(InputText(label="Config JSON", style=discord.InputTextStyle.long, required=False))
		self.add_item(InputText(label="Qualifier ID", style=discord.InputTextStyle.short, required=False))

		self.callback = self.callback

	async def callback(self, interaction: discord.Interaction):
		if not self.children[0].value.isdigit():
			await interaction.respond("Values for player ID needs to be an integer")
			self.stop()
			return

		player = await self.sql.getPlayerByID(int(self.children[0].value))
		if player == None:
			await interaction.followup.send("Player for tourney not found")

		chn = None
		isa = None
		conj = None
		qid = None
		try:
			for config in self.children:
				if config.label == "CH Name" and config.value != "":
					chn = config.value
				if config.label == "Is Active" and config.value != "":
					isa = config.value
				if config.label == "Config JSON" and config.value != "":
					conj = json.loads(config.value)
				if config.label == "Qualifier ID" and config.value != "":
					qid = config.value

			await self.sql.replacePlayer(self.children[0].value, None, isa, chn, player['tourneyid'], conj, qid)
		except Exception as e:
			await interaction.respond(f"Failed to set config: {e}", ephemeral=True)
			self.stop()
			return

		await interaction.respond("Successfully set whatever you sent me :shrug:", ephemeral=True, delete_after=5)
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

	@owner.command(name='reftoolmatchadd', description='Submit a refmatch entry for testing', integration_types={discord.IntegrationType.guild_install})
	@commands.is_owner()
	async def setTourney(self, ctx):
		modal = TourneyMatchInProcessModal(self.bot.tourneyDB, title="Reftool match add")
		await ctx.send_modal(modal=modal)

	@owner.command(name='playerconfig', description='Set config settings for a player', integration_types={discord.IntegrationType.guild_install})
	@commands.is_owner()
	async def setPlayer(self, ctx):
		modal = PlayerModal(self.bot.tourneyDB, title="Player config settngs")
		await ctx.send_modal(modal=modal)

	@commands.Cog.listener()
	async def on_application_command_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
		if isinstance(error, commands.NotOwner):
			await ctx.respond("You don't own me! (You cannot run this command)", ephemeral=True)
		else:
			raise error

def setup(bot):
	bot.add_cog(OwnerCmds(bot))