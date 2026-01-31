import json
import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

from corpoch.models import Tournament, TournamentBracket, TournamentPlayer, TournamentQualifier

class TourneyConfigModal(Modal):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.add_item(InputText(label="ID", style=discord.InputTextStyle.short, required=False))
		self.add_item(InputText(label="Tourney Config", style=discord.InputTextStyle.long, required=False))
		self.add_item(InputText(label="Qualifier Config", style=discord.InputTextStyle.long, required=False))

	async def callback(self, interaction: discord.Interaction):
		if self.children[0].label == 'ID' and self.children[0].value > -1:
			tourney = Tournament.objects.get(id=self.children[0].value)
		elif self.children[0].label == 'ID' and self.children[0].value == -1:
			tourney = Tournament(interaction.guild.id, active=True)
		else:
			tourney = Tournament.objects.get(serverid=interaction.guild.id, active=True)

		if tourney == None:
			print("OWNER: Tourney conf: no tourney found")
			await interaction.respond("Tournament not found, and id not -1 for creation", ephemeral=True, delete_after=5)
			return
			
		try:
			for config in self.children:
				if config.label == "Tourney Config" and config.value != "":
					tourney.config = json.loads(config.value)
				if config.label == "Qualifier Config" and config.value != "":
					tourney.qualifier_config = json.loads(config.value)

			tourney.save()
		except Exception as e:
			await interaction.respond(f"Failed to set config: {e}", ephemeral=True)
			self.stop()
			return

		await interaction.respond("Successfully set whatever you sent me :shrug:", ephemeral=True, delete_after=5)
		self.stop()

class TourneyBracketModal(Modal):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.add_item(InputText(label="ID", style=discord.InputTextStyle.short, required=False))
		self.add_item(InputText(label="Bracket Config", style=discord.InputTextStyle.long, required=False))
		self.add_item(InputText(label="Bracket Setlist", style=discord.InputTextStyle.long, required=False))
		self.add_item(InputText)

	async def callback(self, interaction: discord.Interaction):
		tourney = Tournament.objects.get(serverid=interaction.guild.id, active=True)
		if tourney == None:
			print("OWNER: Bracket conf: no tourney found")
			await interaction.respond("Active tournament not found", ephemeral=True, delete_after=5)
			return

		if self.children[0].label == 'ID' and self.children[0].value > -1:
			bracket = TournamentBracket.objects.get(id=self.children[0].value)
		elif self.children[0].label == 'ID' and self.children[0].value == -1:
			bracket = TournamentBracket(tournament=tourney)
		else:
			bracket = TournamentBracket.objects.filter(tournament=tourney, active=True)[0]

		if bracket == None:
			print("OWNER: Bracket conf: no tourney found")
			await interaction.respond("Tournament not found, and id not -1 for creation", ephemeral=True, delete_after=5)
			return

		try:
			for config in self.children:
				if config.label == "Bracket Config" and config.value != "":
					bracket.config = json.loads(config.value)
				if config.label == "Bracket Setlist" and config.value != "":
					bracket.qualifier_config = json.loads(config.value)

			bracket.save()
		except Exception as e:
			await interaction.respond(f"Failed to set config: {e}", ephemeral=True)
			self.stop()
			return

		await interaction.respond("Successfully set whatever you sent me :shrug:", ephemeral=True, delete_after=5)
		self.stop()

class TourneyMatchInProcessModal(Modal):
	def __init__(self, *args, **kwargs):
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

		player = TournamentPlayer.objects.filter(id=int(self.children[0].value))
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
		modal = TourneyConfigModal(title="Mindful of the 4000 limit!")
		await ctx.send_modal(modal=modal)

	@owner.command(name='reftoolmatchadd', description='Submit a refmatch entry for testing', integration_types={discord.IntegrationType.guild_install})
	@commands.is_owner()
	async def setTourney(self, ctx):
		modal = TourneyMatchInProcessModal(title="Reftool match add")
		await ctx.send_modal(modal=modal)

	@owner.command(name='playerconfig', description='Set config settings for a player', integration_types={discord.IntegrationType.guild_install})
	@commands.is_owner()
	async def setPlayer(self, ctx):
		modal = PlayerModal(title="Player config settngs")
		await ctx.send_modal(modal=modal)

	@commands.Cog.listener()
	async def on_application_command_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
		if isinstance(error, commands.NotOwner):
			await ctx.respond("You don't own me! (You cannot run this command)", ephemeral=True)
		else:
			raise error

def setup(bot):
	bot.add_cog(OwnerCmds(bot))