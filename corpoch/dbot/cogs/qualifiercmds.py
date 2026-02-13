import json, base64, io, os

import discord
import pytz
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from django.db.models.functions import Now
from asgiref.sync import sync_to_async
from django.utils import timezone
from django.core.files.base import ContentFile

from corpoch.models import Tournament, TournamentBracket, TournamentPlayer, Qualifier, QualifierSubmission
from corpoch.providers import CHOpt, CHStegTool

class QualifierSelect(discord.ui.Select):
	def __init__(self, quali):
		self.quali = quali
		self.retOpts = {}

	async def init(self):
		qualis = []
		for qualifier in self.quali.qualifiers:
			retOpts[qualifier.name] = bracket
			qualis.append(discord.SelectOption(label=str(qualifier)))
		super().__init__(max_values=1, options=qualis, custom_id="bracket_sel")

	async def callback(self, interaction: discord.Integration):
		qualifier = self.retOpts[self.values[0]]
		if qualifier.channel != self.quali.ctx.channel.id:
			await interaction.respond(f"Please run command in channel (https://discord.com/{self.quali.tourney.guild}/{qualifier.channel}) to submit!", ephemeral=True, delete_after=10)
		else:
			self.quali.qualifier = qualifier

class ScreenshotModal(discord.ui.DesignerModal):
	def __init__(self):
		self.screen = None
		file = discord.ui.Label("Screenshot of your qualifier run to upload", discord.ui.FileUpload(max_values=1, required=True))
		super().__init__(discord.ui.TextDisplay("Screenshot Submission"), file, title="Qualifier Screenshot")

	async def callback(self, interaction: discord.Interaction):
		self.screen = self.children[1].item.values[0]
		await interaction.respond("Processing, wait for embed to update", ephemeral=True, delete_after=5)

class QualiPlayerSel(discord.ui.Select):
	def __init__(self, quali):
		self.quali = quali
		self.retOpts = {}
		opts = []
		for i, player in enumerate(self.quali.steg.output['players']):
			self.retOpts[player['profile_name']] = i
			opts.append(discord.SelectOption(label=player['profile_name']))
		super().__init__(max_values=1, options=opts, custom_id="bracket_sel")

	async def callback(self, interaction: discord.Interaction):
		#Purge all non-selected players from steg data
		self.quali.steg.output['players'] = [ ply for i, ply in enumerate(self.quali.steg.output['players']) if i == self.retOpts[self.values[0]]]

class DiscordQualifierView(discord.ui.View):
	def __init__(self, ctx):
		super().__init__(timeout = None)
		self.ctx = ctx
		self.qualifier = None
		self.qualifiers = []
		self.tourney = None
		self.steg = None
		self.screen = None
		self.doneStartup = False

		cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancelBtn")
		cancel.callback = self.cancelBtn
		self.add_item(cancel)

		upload = discord.ui.Button(label="Upload Screenshot", custom_id="screenBtn")
		upload.callback = self.screenBtn
		self.add_item(upload)

		self.submit = discord.ui.Button(label="Submit", style=discord.ButtonStyle.green, custom_id="submitBtn")
		self.submit.callback = self.submitBtn
		self.submit.disabled = True
		self.add_item(self.submit)

	async def show(self):
		if not self.doneStartup:
			await self.ctx.defer(ephemeral=True)
			try:
				self.tourney = await Tournament.objects.select_related('config').aget(guild=self.ctx.guild.id, active=True)
			except Tournament.DoesNotExist:
				await self.ctx.respond("There are no active tournaments running in this server at this time.", ephemeral=True)
				return

			if not self.qualifier:
				async for qualifier in Qualifier.objects.select_related('chart', 'bracket').all().filter(tournament=self.tourney, end_time__gte=timezone.now()):
					self.qualifiers.append(qualifier)

			try:
				self.ply = await TournamentPlayer.objects.aget(user=self.ctx.user.id)
			except TournamentPlayer.DoesNotExist:
				self.ply = TournamentPlayer(user=self.ctx.user.id, tournament=self.tourney, ch_name="</Null>")

		embeds = []
		if self.qualifier == None and len(self.qualifiers) > 1:
			qualiSel = QualifierSelect(self)
			await qualiSel.init()
			self.add_item(qualiSel)
			embeds.append(self.buildQualiSelEmbed())
		elif self.qualifier == None and len(self.qualifiers) == 0:
			await self.ctx.respond("There are no active qualifiers running in this server at this time.", ephemeral=True)
			return
		elif self.qualifier == None:#Only one qualifier
				self.qualifier = self.qualifiers[0]

		if self.qualifier:
			embeds.append(self.buildRulesEmbed())

		if self.steg:
			embeds.append(self.steg.buildStatsEmbed("Qualifier Submission"))
			if len(self.steg.output['players']) > 1:
				embeds.append(self.buildPlySelEmbed())
				self.add_item(QualiPlayerSel(self))
			else:
				if self.ply.ch_name == "</Null>":
					embeds.append(self.buildNoticeEmbed())
				embeds.append(self.buildSubmitEmbed())
				self.submit.disabled = False
			
		if not self.doneStartup:
			self.doneStartup = True
			await self.ctx.respond(embeds=embeds, view=self)
		else:
			await self.ctx.edit(embeds=embeds, view=self)

	async def cancelBtn(self, interaction: discord.Interaction):
		await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
		self.stop()

	async def screenBtn(self, interaction: discord.Interaction):
		modal = ScreenshotModal()
		await interaction.response.send_modal(modal=modal)
		await modal.wait()
		steg = CHStegTool()
		await steg.getStegInfo(modal.screen)
		plySteg = []
		for i, ply in enumerate(steg.output['players']):
			try:
				otherPly = await TournamentPlayer.objects.aget(ch_name=ply['profile_name'])
				if self.ply and self.ply != otherPly:
					print(f"Removing player {ply['profile_name']} already in tournament {self.tourney.short_name}")
					continue
			except TournamentPlayer.DoesNotExist:
				pass

			if self.ply.ch_name != "</Null>" and not self.ply.check_ch_name(ply['profile_name']):
					print(f"Stripping {i}:{ply['profile_name']} from {self.ply.ch_name} qualifier screen")
					continue

			plySteg.append(ply)

		steg.output['players'] = plySteg
		if steg.output['checksum'] != self.qualifier.chart.md5:
			await interaction.followup.send("Screenshot is not for the qualifier chart.", ephemeral=True, delete_after=5)
		elif steg.output['game_version'] != self.tourney.config.version:
			await interaction.followup.send(f"Qualifier is not Clone Hero version {self.tourney.config.version}", ephemeral=True, delete_after=5)
		elif steg.output['playback_speed'] != self.qualifier.chart.speed:
			await interaction.followup.send(f"Qualifier is not ran at the right speed of {self.qualifier.chart.speed}%", ephemeral=True, delete_after=5)
		else:
			self.steg = steg
			self.screen = modal.screen
		await self.show()

	async def submitBtn(self, interaction: discord.Interaction):
		await interaction.response.defer()
		self.steg.output['players'][0]['score_timestamp'] = self.steg.output['score_timestamp'] #Copy into player row for slicing out metadata
		self.ply.ch_name = self.steg.output['players'][0]['profile_name']
		await self.ply.asave()
		quali = QualifierSubmission(player=self.ply, qualifier=self.qualifier, steg=self.steg.output['players'][0])
		await sync_to_async(quali.screenshot.save)(f'{uuid.uuid1()}.png', open(self.steg.img_path, 'rb'))
		await quali.asave()
		await self.ctx.interaction.delete_original_response()
		tmp = await sync_to_async(lambda: self.qualifier.tournament)()
		await interaction.followup.send(f"{self.ctx.user.mention} submitted a qualifier for {self.qualifier}!", ephemeral=False)

	def buildQualiSelEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0xFF8000)
		embed.title = "Multiple active qualifiers!"
		embed.add_field(name="Directions", value="Pick a qualifier to submit for.")
		return embed

	def buildPlySelEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0xFF8000)
		embed.title = "Multiple players in qualifier screenshot!"
		embed.add_field(name="Directions", value="In the drop-down below, pick which player you are.")
		return embed

	def buildNoticeEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0xEEFF00)
		embed.title = "Notices"
		embed.add_field(name="Player Name", value="The player-name in this submission will be used to track progress through this tournament\nYou will need to use it for all official matches (minus formatting/spaces)", inline=False)
		embed.add_field(name="Screenshots Notice", value="Matches for this tournament will be tracked using in-game taken screenshots.\nPlease ensure that you have automatic screenshots enabled!", inline=False)
		return embed

	def buildSubmitEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0xEEFF00)
		embed.title = "Submit"
		embed.add_field(name="Directions", value="If you agree to everything, hit submit to complete your submission!", inline=False)
		return embed

	def buildRulesEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0xFF2800)
		embed.title = "Qualifier Submission Rules"
		embed.add_field(name=f"{self.tourney.name} Rules", value=self.tourney.config.rules, inline=False)
		embed.add_field(name=f"Qualifier Rules", value=self.qualifier.rules, inline=False)

		if self.qualifier.form_link and self.qualifier.form_link != "":
			embed.add_field(name="Qualifier Form Link", value=f"[Link Here]({self.qualifier.form_link})", inline=False)

		embed.add_field(name="Qualifier Chart Link", value=f"[Link Here]({self.qualifier.chart.url})", inline=False)
		embed.add_field(name="Agreement", value="By submitting a qualifier, you are agreeing to these rules")


		#TODO - add 

		return embed

class QualifierCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	qualifier = discord.SlashCommandGroup('qualifier','Clone Hero Tournament Qualifer Commands')

	#TODO: Make a /qualifier path cmd?

	@qualifier.command(name='submit', description='Submit a qualifier score for a tournament this server is running', integration_types={discord.IntegrationType.guild_install})
	#@discord.option("submission", discord.Attachment, description="Attach in-game screenshot of qualifer run", required=True)
	async def qualifierSubmitCmd(self, ctx):#, submission: discord.Attachment):
		view = DiscordQualifierView(ctx)
		await view.show()
	
	@qualifier.command(name='status', description='Shows the status of your qualifier for an active tournament', integration_types={discord.IntegrationType.guild_install})
	async def qualifierSubmitCmd(self, ctx):
		view = DiscordQualifierView(ctx)
		await view.init()

	@qualifier.command(name='info', description='Shows the info for an active tournament qualifier', integration_types={discord.IntegrationType.guild_install})
	async def qualifierSubmitCmd(self, ctx):
		view = DiscordQualifierView(ctx)
		await view.init()

	@commands.Cog.listener()
	async def on_application_command_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
		if isinstance(error, commands.NotOwner):
			await ctx.respond("You don't own me! (You cannot run this command)", ephemeral=True)
		else:
			raise error

def setup(bot):
	bot.add_cog(QualifierCmds(bot))
