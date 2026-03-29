import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from asgiref.sync import sync_to_async

from corpoch.providers import CHOpt, EncoreClient, CHStegTool, Hydra
from corpoch.models import Tournament, Chart
from corpoch.types import CH_INSTRUMENTS, CH_DIFFICULTIES
from corpoch.dbot.models import CHEmoji
from corpoch.dbot.view.helpers import get_chart_emoji

class CHOptModal(discord.ui.DesignerModal):
	def __init__(self, path, *args, **kwargs):
		self.path = path
		args += (discord.ui.Label("Squeeze % (0-100)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value='0')),)
		args += (discord.ui.Label("Early Whammy % (0-100)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value='0')),)
		args += (discord.ui.Label("Lazy Whammy (ms 0-10000)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value='0')),)
		args += (discord.ui.Label("Whammy Delay (ms 0-10000)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value='0')),)
		if not isinstance(self.path.chart, Chart):
			args += (discord.ui.Label("Song Speed (10-500)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value=100)),)
		super().__init__(*args, **kwargs)
		self.title = "CHOpt Options"

	async def callback(self, interaction: discord.Interaction):
		if not self.children[0].item.value.isdigit() or not (0 <= int(self.children[0].item.value) <= 100):
			await interaction.response.send_message("Invalid whammy value, please use a number between 0 and 100", ephemeral=True)
			self.stop()
			return
		else:
			self.path.chopt.opts.squeeze = int(self.children[0].item.value)

		if not self.children[1].item.value.isdigit() or not (0 <= int(self.children[1].item.value) <= 100):
			await interaction.response.send_message("Invalid squeeze value, please use a number between 0 and 100", ephemeral=True)
			self.stop()
			return
		else:
			self.path.chopt.opts.whammy = int(self.children[1].item.value)

		if not self.children[2].item.value.isdigit() or not (0 <= int(self.children[2].item.value) <= 10000):
			await interaction.response.send_message("Invalid lazy whammy value, please use a number between 0 and 10000", ephemeral=True)
			self.stop()
			return
		else:
			self.path.chopt.opts.lazy = int(self.children[2].item.value)

		if not self.children[3].item.value.isdigit() or not (0 <= int(self.children[3].item.value) <= 10000):
			await interaction.response.send_message("Invalid whammy delay value, please use a number between 0 and 10000", ephemeral=True)
			self.stop()
			return
		else:
			self.path.chopt.opts.delay = int(self.children[3].item.value)

		if len(self.children) == 5:
			if not self.children[4].item.value.isdigit() or not (10 <= int(self.children[4].item.value) <= 500):
				await interaction.response.send_message("Invalid speed value, please use a number between 10 and 500", ephemeral=True)
				self.stop()
				return
			else:
				self.path.chopt.opts.speed = int(self.children[4].item.value)

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
					self.path.chopt.opts.instrument = inst
					break

		await interaction.response.defer(invisible=True)
		tmp = self.path.encore.search(retData)
		self.path.charts = tmp.data
		await self.path.show()
		self.stop()

class TournamentSelect(discord.ui.Select):
	def __init__(self, path):
		self.path = path
		self.retOpts = {}
		#TODO - Move this to a discord autocomplete text field - I *think* that can allow for only options that exist, but sidestep the 24 limit here
	async def init(self):
		opts = []
		async for tourney in Tournament.objects.all():
			if not await sync_to_async(tourney.has_revealed_setlist)():
				continue

			self.retOpts[tourney.name] = tourney
			if self.path.ctx.guild == None:
				opts.append(discord.SelectOption(label=tourney.name, description=tourney.short_name, default=True if self.path.tournament and tourney == self.path.tournament else None))
			elif (self.path.tournament == tourney) or (not self.path.tournament and tourney.guild == self.path.ctx.guild.id and tourney.active):
				opts.append(discord.SelectOption(label=tourney.name, description=tourney.short_name, default=True))
				self.path.tournament = tourney
			else:
				opts.append(discord.SelectOption(label=tourney.name, description=tourney.short_name))

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
			if bracket.revealed:
				self.retOpts[str(bracket)] = bracket
				opts.append(discord.SelectOption(label=str(bracket), default=True if self.path.bracket == bracket else False))

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
			emoji = await get_chart_emoji(self.path.bot, chart)
			if isinstance(chart, Chart):
				self.retOpts[chart.md5] = chart
				opts.append(discord.SelectOption(label=chart.tournament_name, emoji=emoji, value=chart.md5, description=f"{'TB - ' if chart.tiebreaker else ''}{chart.artist} - {chart.album} - {chart.charter}"))
			else:
				opts.append(discord.SelectOption(label=chart.name, emoji=emoji, value=chart.md5, description=f"{chart.artist} - {chart.album} - {chart.charter}"))
				self.retOpts[chart.md5] = chart
		super().__init__(placeholder="Select a chart", options=opts, min_values=1, max_values=len(opts), custom_id="chart_sel")

	async def callback(self, interaction: discord.Interaction):
		for retChart in self.values:
			chart = self.retOpts[retChart]
			self.path.chart_paths.append(chart)
			if isinstance(chart, Chart):
				self.path.chopt.opts.instrument = chart.instrument
			self.path.chopt.opts.speed = chart.speed

		await interaction.response.defer(ephemeral=True)
		await self.path.show()

class PathView(discord.ui.View):
	def __init__(self, path):
		self.path = path
		super().__init__(timeout = None)
		if len(self.path.chart_paths) < 1:
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
		#May be good to set the "default" tournament to discord guild - removed as it caused issues w/ empty setlist tournaments
		self.path.tournament = None
		self.path.bracket = None
		self.charts = []
		await interaction.response.defer(invisible=True)
		await self.path.show()

	@discord.ui.button(label='Options', style=discord.ButtonStyle.secondary, custom_id="opts")
	async def optsBtn(self, button, interaction: discord.Interaction):
		if self.path.chopt.opts.instrument[0] == 'drums':
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
