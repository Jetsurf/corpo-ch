import discord, os, sys, json, shutil

from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from asgiref.sync import sync_to_async

from corpoch.providers import CHOpt, EncoreClient, CHStegTool, Hydra
from corpoch.models import Tournament, TournamentBracket, Chart, CH_INSTRUMENTS, CH_DIFFICULTIES
from corpoch.dbot.models import CHEmoji

class CHOptModal(discord.ui.DesignerModal):
	def __init__(self, path, *args, **kwargs):
		self.path = path
		args += (discord.ui.Label("Early Whammy % (0-100)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value='0')),)
		args += (discord.ui.Label("Squeeze % (0-100)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value='0')),)
		args += (discord.ui.Label("Song Speed (0-1000)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value=100)),)
		args += (discord.ui.Label("Lazy Whammy (ms 0-10000)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value='0')),)
		args += (discord.ui.Label("Whammy Delay (ms 0-10000)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value='0')),)
		super().__init__(*args, **kwargs)
		self.title = "CHOpt Options"

	async def callback(self, interaction: discord.Interaction):
		if not self.children[1].item.value.isdigit() and not int(self.children[0].item.value) >= 0 or not int(self.children[0].item.value) <= 100:
			await interaction.response.send_message("Invalid whammy value, please use a number between 0 and 100", ephemeral=True)
			self.stop()
			return
		else:
			self.path.chopt.opts.whammy = int(self.children[0].item.value)

		if not self.children[1].item.value.isdigit() and not int(self.children[1].item.value) >= 0 or not int(self.children[1].item.value) <= 100:
			await interaction.response.send_message("Invalid squeeze value, please use a number between 0 and 100", ephemeral=True)
			self.stop()
			return
		else:
			self.path.chopt.opts.squeeze = int(self.children[1].item.value)

		if not self.children[2].item.value.isdigit() and not int(self.children[2].item.value) >= 10 or not int(self.children[2].item.value) <= 1000:
			await interaction.response.send_message("Invalid speed value, please use a number between 10 and 250", ephemeral=True)
			self.stop()
			return
		else:
			self.path.chopt.opts.speed = int(self.children[2].item.value)

		if not self.children[3].item.value.isdigit() and not int(self.children[3].item.value) >= 0 or not int(self.children[3].item.value) <= 10000:
			await interaction.response.send_message("Invalid lazy whammy value, please use a number between 0 and 10000", ephemeral=True)
			self.stop()
			return
		else:
			self.path.chopt.opts.lazy = int(self.children[3].item.value)

		if not self.children[4].item.value.isdigit() and not int(self.children[4].item.value) >= 10 or not int(self.children[4].item.value) <= 10000:
			await interaction.response.send_message("Invalid whammy delay value, please use a number between 0 and 10000", ephemeral=True)
			self.stop()
			return
		else:
			self.path.chopt.opts.delay = int(self.children[4].item.value)

		await interaction.response.defer(invisible=True)
		self.stop()

class HydraModal(discord.ui.DesignerModal):
	def __init__(self, path, *args, **kwargs):
		self.path = path
		args += (discord.ui.Label("Bass/Kick 2x Pedal", discord.ui.Select(max_values=1, options=[discord.SelectOption(label='True', value='True', default=True), discord.SelectOption(label="False", value='False')], required=True)),)
		args += (discord.ui.Label("Pro Drums", discord.ui.Select(max_values=1, options=[discord.SelectOption(label='True', value='True', default=True), discord.SelectOption(label="False", value='False')], required=True)),)
		args += (discord.ui.Label("Depth Mode", discord.ui.Select(max_values=1, options=[discord.SelectOption(label='Scores', value='scores', default=True), discord.SelectOption(label="Points", value='points')], required=True)),)
		args += (discord.ui.Label("Score Depth", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value=self.path.hydra.opts.depth)),)
		#args += (discord.ui.Label("Difficulty", discord.ui.Select(max_values=1, options=[discord.SelectOption(label='True', value='True', default=True), discord.SelectOption(label="False", value='False')], required=True)),)
		super().__init__(discord.ui.TextDisplay("Hydra Options"), *args, **kwargs)

	async def callback(self, interaction: discord.Interaction):
		self.path.hydra.opts.bass2x = True if self.children[1].item.values[0] in "True" else False
		self.path.hydra.opts.pro = True if self.children[2].item.values[0] in "True" else False
		self.path.hydra.opts.depth_mode = 'scores' if self.children[3].item.values[0] in "scores" else 'points'
		if self.path.hydra.opts.depth_mode == 'points':
			await interaction.response.send_message("Points depth mode disabled for now", delete_after=10, ephemeral=True)
			return
		valid = True
		if not self.children[4].item.value.isdigit():
			valid = False
		elif self.path.hydra.opts.depth_mode == "scores" and (int(self.children[4].item.value) < 1 or int(self.children[4].item.value) > 10):
			valid = False
		elif self.path.hydra.opts.depth_mode == "points" and (int(self.children[4].item.value) < 1 or int(self.children[4].item.value) > 10000000):
			valid = False

		if not valid:
			if self.path.hydra.opts.depth_mode == "scores":
				await interaction.response.send_message("Invalid depth - must be 1-10 for Depth Mode: Score", delete_after=10, ephemeral=True)
			else:
				await interaction.response.send_message("Invalid depth - must be 1-10,000,000 for Depth Mode: Points", delete_after=10, ephemeral=True)
		else:
			self.path.hydra.opts.depth = int(self.children[4].item.value)
			await interaction.response.defer(invisible=True)
		self.stop()

class EncoreModal(discord.ui.DesignerModal):
	def __init__(self, path, *args, **kwargs):
		self.path = path
		args += (discord.ui.Label("Song Name", discord.ui.InputText(style=discord.InputTextStyle.short, required=True)),)
		args += (discord.ui.Label("Artist", discord.ui.InputText(style=discord.InputTextStyle.short, required=False)),)
		args += (discord.ui.Label("Album", discord.ui.InputText(style=discord.InputTextStyle.short, required=False)),)
		args += (discord.ui.Label("Charter", discord.ui.InputText(style=discord.InputTextStyle.short, required=False)),)
		instSel = discord.ui.Select(max_values=1, options=[], required=True)
		for inst in CH_INSTRUMENTS:
			instSel.options.append(discord.SelectOption(label=inst[1], value=inst[0], default=True if inst[0] in 'guitar' else False))
		args += (discord.ui.Label("Instrument", instSel),)
		super().__init__(*args, **kwargs)

	async def callback(self, interaction: discord.Interaction):
		retData = {}
		retData['name'] = self.children[0].item.value
		if self.children[1].item.value:
			retData['artist'] = self.children[1].item.value
		if self.children[2].item.value:
			retData['album'] = self.children[2].item.value
		if self.children[3].item.value:
			retData['charter'] = self.children[3].item.value
		if self.children[4].item.values[0]:
			retData['instrument'] = self.children[4].item.values[0]
			for inst in CH_INSTRUMENTS:
				if inst[0] == self.children[4].item.values[0]:
					self.path.instrument = inst
					self.path.chopt.opts.instrument = inst
					break

		await interaction.response.defer(invisible=True)
		tmp = self.path.encore.search(retData)
		self.path.charts = tmp
		await self.path.show()
		self.stop()

class TournamentSelect(discord.ui.Select):
	def __init__(self, path):
		self.path = path
		self.retOpts = {}
		#TODO - Move this to a discord autocomplete text field - I *think* that can allow for only options that exist, but sidestep the 24 limit here
	async def init(self):		
		active = None
		opts = []
		async for tourney in Tournament.objects.all():
			lenB = len([b async for b in tourney.brackets.select_related()])
			hasSetlist = False
			if lenB == 0:
				continue
			if lenB > 0:
				async for bracket in tourney.brackets.select_related():
					lenC = len([b async for b in bracket.setlist.select_related()])
					if lenC > 0:
						hasSetlist = True
						break

			if not hasSetlist:
				continue
						
			self.retOpts[tourney.name] = tourney
			if not self.path.tournament and tourney.guild == self.path.ctx.guild.id and tourney.active:
				opts.append(discord.SelectOption(label=tourney.name, description=tourney.short_name))
				active = tourney
			elif self.path.tournament == tourney:
				opts.append(discord.SelectOption(label=tourney.name, description=tourney.short_name))
				active = tourney
			else:
				opts.append(discord.SelectOption(label=tourney.name, description=tourney.short_name))
		
		if active:
			super().__init__(placeholder=str(active), options=opts, custom_id="tourney_sel")
		else:
			super().__init__(placeholder="Select a tournament", options=opts, custom_id="tourney_sel")

	async def callback(self, interaction: discord.Interaction):
		self.path.tournament = self.retOpts[self.values[0]]
		await interaction.response.defer(ephemeral=True)
		await self.path.show()

class BracketSelect(discord.ui.Select):
	def __init__(self, path):
		self.path = path
		self.retOpts = {}

	async def init(self):
		opts = []
		async for bracket in self.path.tournament.brackets.select_related():
			self.retOpts[str(bracket)] = bracket
			opts.append(discord.SelectOption(label=str(bracket)))

		if self.path.bracket:
			super().__init__(placeholder=str(self.path.bracket), options=opts, custom_id="bracket_sel")
		else:
			super().__init__(placeholder="Select a bracket", options=opts, custom_id="bracket_sel")

	async def callback(self, interaction: discord.Interaction):
		self.path.bracket = self.retOpts[self.values[0]]
		self.path.charts = [ chart async for chart in self.path.bracket.setlist.select_related().all() ]
		await interaction.response.defer(ephemeral=True)
		await self.path.show()

class ChartSelect(discord.ui.Select):
	def __init__(self, path):
		self.path = path
		self.retOpts = {}

	async def init(self):
		opts = []
		for chart in self.path.charts:
			if isinstance(chart, Chart):
				self.retOpts[chart.md5] = chart
				icon = await sync_to_async(lambda: chart.icon)()
				try:
					icon = await CHEmoji.objects.select_related().aget(icon_id=chart.icon)
				except CHEmoji.DoesNotExist:
					icon = await CHEmoji.objects.select_related().aget(icon_id='ch')
				emoji = await self.path.bot.fetch_emoji(icon.id)
				opts.append(discord.SelectOption(label=chart.name, emoji=emoji, value=chart.md5, description=f"{chart.artist} - {chart.album} - {chart.charter}", default=True if self.path.chart == chart else False))
			else:#dict
				try:
					icon = await CHEmoji.objects.select_related().aget(icon_id=chart['icon'])
				except CHEmoji.DoesNotExist:
					icon = await CHEmoji.objects.select_related().aget(icon_id='ch')

				emoji = await self.path.bot.fetch_emoji(icon.id)
				opts.append(discord.SelectOption(label=chart['name'], emoji=emoji if emoji else None, value=chart['md5'], description=f"{chart['artist']} - {chart['album']} - {chart['charter']}"))
				self.retOpts[chart['md5']] = chart

		if self.path.chart:
			if isinstance(self.path.chart, Chart):
				super().__init__(placeholder=self.path.chart.name, options=opts, max_values=1, custom_id="chart_sel")
			else:
				super().__init__(placeholder=self.path.chart['name'], options=opts, max_values=1, custom_id="chart_sel")
		else:
			super().__init__(placeholder="Select a chart", options=opts, max_values=1, custom_id="chart_sel")

	async def callback(self, interaction: discord.Interaction):
		self.path.chart = self.retOpts[self.values[0]]

		await interaction.response.defer(ephemeral=True)
		await self.path.show()

class Path():
	def __init__(self, bot, ctx):
		self.bot = bot
		self.ctx = ctx
		self.user = ctx.user
		self.encore = EncoreClient(exact=False)
		self.instrument = "guitar"
		self.chopt = CHOpt()
		self.hydra = Hydra()
		#self.tournament = None #Here as a kindness - presence of these attrs flags touney search enabled
		#self.bracket = None
		self.charts = []
		self.chart = None

	async def show(self):
		view = PathView(self)
		await view.init()
		await self.ctx.interaction.edit_original_response(embeds=[self.genChartEmbed()], content=None, view=view)

	async def hide(self):
		await self.ctx.interaction.delete_original_response()

	async def showResult(self, interaction):
		if self.instrument[0] == 'drums':
			self.hydra.gen_path(self.chart)
			if not self.hydra.output:
				await interaction.followup.send("Path generation died on Hydra call.", ephemeral=True)
				await self.hide()		
		else:
			self.chopt.gen_path(self.chart)
			try:
				self.chopt.save_for_upload()
			except:
				pass
			if not self.chopt.url:
				await interaction.followup.send("Path generation died on CHOpt call.", ephemeral=True)
				await self.hide()
		
		if self.instrument[0] == "drums":
			await interaction.followup.send(embed=self.genHydraResultEmbed())
		else:
			await interaction.followup.send(embed=self.genCHOptResultEmbed(), ephemeral=True)
		await self.hide()

	async def doSearch(self, inQuery):
		self.searchData = self.chUtils.encoreSearch(inQuery)
		self.numCharts = len(self.searchData)
		self.selection = 1 if self.numCharts == 1 else -1

	def genInstructionEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "Instructions"
		embed.add_field(name="Steps", value="Use the search button to search for a chart on Encore\nUse the tournament search button to seach through tournament setlists", inline=False)
		return embed

	def genChartEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "CH Path Generator"
		chartListing = ""
		if self.charts:
			embed.add_field(name="Directions", value="Charts shown in dropdown below.\nSelect the one you want to generate a path for.\nSet options, then submit!", inline=False) 
		else:
			embed.add_field(name="Directions", value="No results found for search.\nTry searching again with different options.", inline=False) 

		if self.chart:
			self.addEmbedToolField(embed)

		return embed

	def genEmbedBase(self) -> discord.Embed:
		embed = discord.Embed(colour=0x00F2FF)
		embed.set_author(name=f"Generated by:{self.ctx.user.display_name}", icon_url=self.ctx.user.avatar.url)
		embed.title = "/ch path run result"
		embed.set_author(name=self.ctx.user.display_name, icon_url=self.ctx.user.avatar.url)
		return embed

	def addEmbedToolField(self, embed: discord.Embed):
		if self.instrument[0] == 'drums':
			embed.add_field(name="Hydra Options Used", value=f"Kick/Bass 2x: {self.hydra.opts.bass2x}\nPro Drums: {self.hydra.opts.pro}\nDepth Mode: {self.hydra.opts.depth_mode}\nDepth Value: {self.hydra.opts.depth}", inline=False)
		else:
			embed.add_field(name="CHOpt Options Used", value=f"Early Whammy: {self.chopt.opts.whammy}%\nSqueeze: {self.chopt.opts.squeeze}%\nSong Speed: {self.chopt.opts.speed}%\nLazy Whammy: {self.chopt.opts.lazy}ms\nWhammy Delay: {self.chopt.opts.delay}ms", inline=False)

	def genHydraResultEmbed(self) -> discord.Embed:
		embed = self.genEmbedBase()
		if isinstance(self.chart, Chart):
			embed.add_field(name="Hydra Path For", value=f"{self.chart.name} - {self.chart.artist} - {self.chart.album} - {self.chart.charter} - {self.chart.instrument}", inline=False)
		else:
			embed.add_field(name="Hydra Path For", value=f"{self.chart["name"]} - {self.chart["artist"]} - {self.chart["album"]} - {self.chart["charter"]} - {self.instrument[1]}", inline=False)
		pathStr = ""
		for p in self.hydra.output:
			pathStr += f"{p[0]}		{p[1]}\n"
		embed.add_field(name="Path", value=pathStr, inline=False)
		self.addEmbedToolField(embed)
		return embed

	def genCHOptResultEmbed(self) -> discord.Embed:
		embed = self.genEmbedBase()
		embed.set_image(url=self.chopt.url)
		if isinstance(self.chart, Chart):
			embed.add_field(name="CHOpt Path For", value=f"{self.chart.name} - {self.chart.artist} - {self.chart.album} - {self.chart.charter} - {self.chart.instrument}", inline=False)
		else:
			embed.add_field(name="CHOpt Path For", value=f"{self.chart["name"]} - {self.chart["artist"]} - {self.chart["album"]} - {self.chart["charter"]} - {self.instrument[1]}", inline=False)
		self.addEmbedToolField(embed)
		embed.add_field(name="Image Link", value=f"[Link to Image]({self.chopt.url})", inline=False)
		return embed

class PathView(discord.ui.View):
	def __init__(self, path):
		self.path = path
		super().__init__(timeout = None)
		if not self.path.chart:
			self.get_item('submit').disabled = True
			self.get_item('opts').disabled = True

	async def init(self):
		if hasattr(self.path, 'tournament'):
			sel = TournamentSelect(self.path)
			await sel.init()
			self.add_item(sel)
		if hasattr(self.path, 'bracket'):
			sel = BracketSelect(self.path)
			if self.path.tournament != None:
				await sel.init()
				self.add_item(sel)
		if len(self.path.charts) > 0:
			sel = ChartSelect(self.path)
			await sel.init()
			self.add_item(sel)

	async def clear(self):
		if hasattr(self.path, "tournament"):
			del self.path.tournament
		if hasattr(self.path, "bracket"):
			del self.path.bracket
		self.path.charts = []

	@discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancel")
	async def cancelBtn(self, button, interaction: discord.Interaction):
		await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
		self.stop()

	@discord.ui.button(label="Search", style=discord.ButtonStyle.secondary)
	async def searchBtn(self, button, interaction: discord.Interaction):
		await self.clear()
		modal = EncoreModal(self.path, title="Encore search for chart")
		await interaction.response.send_modal(modal)
		await modal.wait()
		await self.path.show()

	@discord.ui.button(label="Tourney Search", style=discord.ButtonStyle.secondary, custom_id="tourney")
	async def tourneyBtn(self, button, interaction: discord.Interaction):
		await self.clear()
		#try:
		#	self.path.tournament = await Tournament.objects.aget(guild=self.path.ctx.guild.id, active=True)	
		#except Tournament.DoesNotExist:
		self.path.tournament = None
		self.path.bracket = None
		self.charts = []
		await interaction.response.defer(invisible=True)
		await self.path.show()

	@discord.ui.button(label='Options', style=discord.ButtonStyle.secondary, custom_id="opts")
	async def optsBtn(self, button, interaction: discord.Interaction):
		if self.path.instrument[0] == 'drums':
			optsModal = HydraModal(self.path, title="Options to use for Hydra")
		else:
			optsModal = CHOptModal(self.path, title="Options to use for CHOpt")
		await interaction.response.send_modal(optsModal)
		await optsModal.wait()

		await self.path.show()

	@discord.ui.button(label="Submit", style=discord.ButtonStyle.green, custom_id="submit")
	async def submitBtn(self, button, interaction: discord.Interaction):
		await interaction.response.defer(invisible=False)
		await self.path.showResult(interaction)

class CHCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	ch = discord.SlashCommandGroup('ch','CloneHero tools')

	@ch.command(name='path',description='Generate a path for a given chart on Chorus', integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install})
	async def path(self, ctx):
		path = Path(self.bot, ctx)
		await ctx.respond(content="Setting up", ephemeral=True)
		await path.show()

	@discord.message_command(name='CH Sten',description='Reads CH Sten data from a screenshot posted to a message', integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install})
	async def getScreenSten(self, ctx: discord.ApplicationContext, msg: discord.Message):
		resp = await ctx.defer(invisible=True)
		if len(msg.attachments) < 1:
			await ctx.respond("No screenshot attached to this post!", delete_after=10)
		elif len(msg.attachments) >= 1:
			#Only gets first screenshot if multiple are attached
			submission = msg.attachments[0]
		
		steg = CHStegTool()
		stegData = await steg.getStegInfo(submission)

		if stegData == None:
			await ctx.respond("Submitted screenshot is not a valid in-game Clone Hero screenshot", delete_after=10)
			return

		embed = steg.buildStatsEmbed("Screenshot Results")
		if len(msg.attachments) > 1:
			await ctx.respond("Only getting first screenshot data from this message", embed=embed)
		else:
			await ctx.respond(embed=embed)	

def setup(bot):
	bot.add_cog(CHCmds(bot))
