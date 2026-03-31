import discord, uuid, json, re
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from asgiref.sync import sync_to_async
from django.utils import timezone

from corpoch.dbot import settings
from corpoch.providers import CHStegTool
from corpoch.types import StegScreenshot, TB_RULESETS, PICK_RULESETS, BAN_RULESETS
from corpoch.models import Tournament, Chart, Match, MatchRound, TournamentPlayer, MatchRound, MatchBan
from corpoch.dbot.models import CHEmoji
from corpoch.dbot.view.helpers import get_chart_emoji

class MatchScreenModal(discord.ui.DesignerModal):
	def __init__(self, match):
		self.match = match
		self.screens = None
		file = discord.ui.Label("Match Screenshot Submission", discord.ui.FileUpload(max_values=len(self.match.rounds), required=True))
		super().__init__(discord.ui.TextDisplay("Screenshots"), file, title="Qualifier Screenshot")

	async def callback(self, interaction: discord.Interaction):
		await interaction.respond("Processing, wait for embed to update", ephemeral=True, delete_after=10)
		self.screens = self.children[1].item.values
		self.stop()

class BanSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		self.retOpts = {}

	async def init(self):
		self.index = (self.match.bracket.ruleset.num_bans - len(self.match.bans) % self.match.bracket.ruleset.num_players) - 1
		opts = []
		if len(self.match.rounds) >= self.match.bracket.ruleset.num_rounds:
			charts = self.match.setlist.select_related('icon').filter(tiebreaker=True)
		else:
			charts = self.match.setlist.select_related('icon').filter(tiebreaker=False).exclude(bans__in=self.match.bans)
		async for chart in charts:
			emoji = await get_chart_emoji(self.match.bot, chart)
			self.retOpts[chart.md5] = chart
			opts.append(discord.SelectOption(label=str(chart.tournament_name), description=f"{chart.artist} - {chart.charter}", emoji=emoji, value=chart.md5))
		if len(self.match.rounds) == self.match.bracket.ruleset.num_rounds:
			super().__init__(placeholder=f"{await sync_to_async(lambda: self.match.rounds[-2].winner.ch_name)()} Ban", max_values=1, options=opts, custom_id="ban_sel")
		else:
			super().__init__(placeholder=f"{await sync_to_async(lambda: self.match.seeding[self.index].player.ch_name)()} Ban", max_values=1, options=opts, custom_id="ban_sel")

	async def callback(self, interaction: discord.Interaction):
		chart = self.retOpts[self.values[0]]
		if len(self.match.rounds) < self.match.bracket.ruleset.num_rounds:
			seed = self.match.seeding[self.index]
		else:
			if self.match.seeding[0].player == self.match.rounds[-2].winner:
				seed = self.match.seeding[0]
			else:
				seed = self.match.seeding[1]
		newBan = MatchBan(num=len(self.match.bans), player=seed, chart=chart, match=self.match.matchDb)
		await newBan.asave()
		self.match.bans.append(newBan)
		await self.match.showTool(interaction)

class SongRoundSelect(discord.ui.Select):
	def __init__(self, match, disabled):
		self.match = match
		self.round = self.match.rounds[-1]
		self.dis = disabled
		self.retOpts = {}

	async def init(self):
		selStr = ""
		if len(self.match.rounds) == 1:
			selStr += f"{self.match.seeding[0].player.ch_name} Picks"
		elif len(self.match.rounds) == self.match.bracket.ruleset.num_rounds and self.match.bracket.ruleset.tb_ruleset == 'refdecide':
			selStr += f"Chat Picks"
		elif self.match.bracket.ruleset.pick_ruleset == "loserpicks":
			selStr += f"{self.match.rounds[-2].loser.ch_name} Picks"
		else:
			prevPicked = self.match.rounds[-1].loser
			picked = list(self.match.seeding).difference(self.match.rounds[-1].picked)[0]
			selStr += f"{picked.ch_name} Picks"

		if self.round.chart:
			selStr += f" - {self.round.chart.name}"

		bansDone = []
		for ban in self.match.bans:
			bansDone.append(ban.chart.id)

		songOptsDone = []
		if len(self.match.rounds) == self.match.bracket.ruleset.num_rounds:
			if self.match.bracket.ruleset.tb_ruleset == 'refdecide':
				for rnd in self.match.rounds:
					chart = await sync_to_async(lambda: rnd.chart)()
					if chart:
						songOptsDone.append(chart.id)
				charts = self.match.setlist.select_related('icon').filter().exclude(id__in=bansDone).exclude(id__in=songOptsDone)
			elif self.match.bracket.ruleset.tb_ruleset == "banpick":
				charts = self.match.setlist.select_related('icon').filter(tiebreaker=True).exclude(id__in=bansDone)
			else:
				charts = self.match.setlist.select_related('icon').filter(tiebreaker=True)
		else:
			for rnd in self.match.rounds:
				chart = await sync_to_async(lambda: rnd.chart)()
				if chart:
					songOptsDone.append(chart.id)
			charts = self.match.setlist.select_related('icon').filter(tiebreaker=False).exclude(id__in=songOptsDone).exclude(id__in=bansDone)

		opts = []
		async for chart in charts:
			self.retOpts[chart.md5] = chart
			emoji = await get_chart_emoji(self.match.bot, chart)
			opts.append(discord.SelectOption(label=chart.tournament_name, value=chart.md5,description=f"{chart.artist} - {chart.charter}", emoji=emoji))
		super().__init__(placeholder=selStr, max_values=1, options=opts, custom_id="roundsong_sel", disabled=self.dis)

	async def callback(self, interaction: discord.Integration):
		self.round.chart = self.retOpts[self.values[0]]
		await self.round.asave()
		await self.match.showTool(interaction)

class PlayerRoundSelect(discord.ui.Select):
	def __init__(self, match, disabled):
		self.match = match
		self.round = self.match.rounds[-1]
		self.dis = disabled
		self.retOpts = {}

	async def init(self):
		opts = []
		for i, seed in enumerate(self.match.seeding):
			auuid = str(uuid.uuid1())
			self.retOpts[auuid] = seed
			opts.append(discord.SelectOption(label=f"{seed.player.ch_name} ({seed.seed})", value=auuid, description=f"@{self.match.seeding_discord[i].display_name}"))
		super().__init__(placeholder="Round Winner", max_values=1, options=opts, custom_id="roundwin_sel", disabled=self.dis)

	async def callback(self, interaction: discord.Integration):
		winner = self.retOpts[self.values[0]]
		if winner == self.match.seeding[0]:
			self.round.loser = self.match.seeding[1].player
		else:
			self.round.loser = self.match.seeding[0].player
		self.round.winner = winner.player
		await self.match.add_round()
		await self.match.showTool(interaction)

class BracketSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		self.retOpts = {}

	async def init(self):
		brackets = []
		async for bracket in self.match.tourney.brackets.select_related('ruleset').all().filter(is_active=True):
			self.retOpts[bracket.name] = bracket
			brackets.append(discord.SelectOption(label=bracket.name))
		super().__init__(max_values=1, options=brackets, custom_id="bracket_sel")

	async def callback(self, interaction: discord.Integration):
		self.match.bracket = self.retOpts[self.values[0]]
		await self.match.showTool(interaction)

class GroupSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		self.retOpts = {}

	async def init(self):
		groups = []
		async for group in self.match.bracket.groups.select_related().all():
			self.retOpts[group.name] = group
			groups.append(discord.SelectOption(label=group.name))
		super().__init__(max_values=1, options=groups, custom_id="group_sel")

	async def callback(self, interaction: discord.Integration):
		self.match.group = self.retOpts[self.values[0]]
		self.match.matchDb = Match(id=uuid.uuid1(), group=self.match.group)
		await self.match.matchDb.asave()
		print(f"REF: {self.match.referee.global_name} starting match {self.match.matchDb.id}")
		await self.match.showTool(interaction)

class PlayerSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		self.retOpts = {}

	async def init(self):
		seeding = []
		async for seed in self.match.group.seeding.select_related('player').all():
			if seed.player.is_active:
				self.retOpts[str(seed.player.user.id)] = seed
				mem = await self.match.guild.fetch_member(seed.player.user.id)
				seeding.append(discord.SelectOption(label=f"{seed.player.ch_name} ({seed.seed})", value=str(seed.player.user.id), description=f"@{mem.display_name}"))
		plys = self.match.bracket.ruleset.num_players
		super().__init__(placeholder="Players", min_values=plys, max_values=plys, options=seeding, custom_id="player_sel")

	async def callback(self, interaction: discord.Interaction):
		self.values.sort()
		for ply in self.values:
			seed = self.retOpts[ply]
			self.match.seeding.append(seed)
			self.match.seeding_discord.append(await self.match.guild.fetch_member(seed.player.user.id))
		await self.match.showTool(interaction)

class DiscordMatchView(discord.ui.View):
	def __init__(self, match):
		super().__init__(timeout = None)
		self.match = match
		self.referee = match.referee

		self.cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancelBtn")
		self.cancel.callback = self.cancelBtn

		self.back = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="backBtn")
		self.back.callback = self.backBtn

		self.defer = discord.ui.Button(label="Defer", style=discord.ButtonStyle.secondary, custom_id="deferBtn")
		self.defer.callback = self.deferBtn

		self.plyin = discord.ui.Button(label="Allow player input", style=discord.ButtonStyle.secondary, custom_id="plyinBtn")
		self.plyin.callback = self.plyinBtn # Future idea

		self.upload = discord.ui.Button(label="Upload Screenshots", style=discord.ButtonStyle.secondary, custom_id="uploadBtn")
		self.upload.callback = self.uploadBtn

		self.submit = discord.ui.Button(label='Submit Match', style=discord.ButtonStyle.green, custom_id="submitBtn")
		self.submit.callback = self.submitBtn
		self.submit.disabled = True

	async def setup_round_player_sels(self):
		sngDis = True if self.match.rounds[-1].chart else False
		sngSel = SongRoundSelect(self.match, sngDis)
		plyDis = True if not self.match.rounds[-1].chart else False
		plySel = PlayerRoundSelect(self.match, plyDis)
		await sngSel.init()
		await plySel.init()
		self.add_item(sngSel)
		self.add_item(plySel)

	async def init(self):
		if self.match.matchDb and self.match.matchDb.complete:
			self.add_item(self.upload)
		else:
			self.add_item(self.cancel)

		if not self.match.bracket:
			sel = BracketSelect(self.match)
			await sel.init()
			self.add_item(sel)
		elif not self.match.group:
			self.add_item(self.back)
			sel = GroupSelect(self.match)
			await sel.init()
			self.add_item(sel)
		elif len(self.match.seeding) < self.match.bracket.ruleset.num_players:
			self.add_item(self.back)
			sel = PlayerSelect(self.match)
			await sel.init()
			self.add_item(sel)
		elif len(self.match.bans) < self.match.bracket.ruleset.total_bans:
			self.add_item(self.back)
			if 'defer' in self.match.bracket.ruleset.ban_ruleset:
				self.add_item(self.defer)
			sel = BanSelect(self.match)
			await sel.init()
			self.add_item(sel)
		elif not self.match.matchDb.complete:
			self.add_item(self.back)
			self.add_item(self.submit)
			if len(self.match.bans) == self.match.bracket.ruleset.total_bans and len(self.match.rounds) == 0:
				await self.match.add_round()

			wins = await self.match.getScore()
			if not await self.match.isFinished() and not await self.match.isTieBreaker():
				await self.setup_round_player_sels()
			elif not await self.match.isFinished() and await self.match.isTieBreaker():
				if self.match.bracket.ruleset.tb_ruleset == 'banpick':
					if len(self.match.bans) == self.match.bracket.ruleset.total_bans:
						sel = BanSelect(self.match)
						await sel.init()
						self.add_item(sel)
					else:
						await self.setup_round_player_sels()
				else:
					await self.setup_round_player_sels()
			elif await self.match.isFinished():
				self.submit.disabled = False

	async def interaction_check(self, interaction: discord.Interaction):
		if interaction.user in self.match.bot.owners:
			return True
		if isinstance(self.match.matchDb, Match) and self.match.matchDb.complete:
			async for seed in self.match.matchDb.players.select_related('player'):
				if seed.player.user.id == interaction.user.id:
					return True
		if interaction.user.id == self.match.referee.id:
			return True
		else:
			await interaction.response.send_message("You are not the ref or player for this match", ephemeral=True, delete_after=10)
			return False

	async def plyinBtn(self, interaction: discord.Interaction):
		pass #To be used in the future to allow ref to have player manually input their choices into the tool

	async def backBtn(self, interaction: discord.Interaction):
		if len(self.match.rounds) > 0:
			if self.match.rounds[-1].chart:
				self.match.rounds[-1].chart = None
			else:
				rnd = self.match.rounds.pop()
				if rnd.id:
					await rnd.adelete()
		elif len(self.match.bans) > 0:
			ban = self.match.bans.pop()
			await ban.adelete()
		elif len(self.match.seeding) > 0:
			self.match.seeding = []
		elif self.match.group:
			await self.match.matchDb.adelete()
			self.match.group = None
		elif self.match.bracket:
			self.match.bracket = None

		await self.match.showTool(interaction)

	async def cancelBtn(self, interaction: discord.Interaction):
		if self.match.confirmCancel:
			await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=10)
			if self.match.matchDb:
				await self.match.matchDb.adelete()
			self.stop()
		else:
			self.match.confirmCancel = True
			await interaction.response.send_message(content="Are you sure you want to cancel? Click cancel again to confirm", ephemeral=True, delete_after=10)

	async def deferBtn(self, interaction: discord.Interaction):
		self.match.matchDb.defer = not self.match.matchDb.defer
		await self.showTool(interaction)

	async def uploadBtn(self, interaction: discord.Interaction):
		modal = MatchScreenModal(self.match)
		await interaction.response.send_modal(modal)
		await modal.wait()
		for screen in modal.screens:
			tool = CHStegTool()
			try:
				steg = await tool.getStegInfo(screen)
				rnd = await MatchRound.objects.select_related('chart').aget(match__id=self.match.matchDb.id, chart__md5=steg.checksum)
				playedChart = rnd.chart
			except MatchRound.DoesNotExist:
				print(f"MATCH SCREENSHOT: {interaction.user.global_name} screenshot {screen.filename} was for a setlist chart not played in this match")
				await interaction.followup.send(f"Screenshot {screen.filename} is for a chart that wasn't played this match.", ephemeral=True, delete_after=10)
				continue
			except Exception as e:
				print(f"MATCH SCREENSHOT: {interaction.user.global_name} screenshot upload failed {screen.filename} to parse: {e}")
				continue

			if playedChart.speed != steg.playback_speed:
				await interaction.followup.send(f"Screenshot {screen.filename} does not match playback speed {steg.playback_speed} for {playedChart.tournament_name}", ephemeral=True, delete_after=10)
				print(f"MATCH SCREENSHOT: {interaction.user.global_name} screenshot {screen.filename} does not match playback speed {steg.playback_speed} for {playedChart.tournament_name}")
				continue
			elif steg.game_version != self.match.bracket.tournament.config.version:
				await interaction.followup.send(f"Screenshot {screen.filename} game version {steg.game_version} does not match tournament {self.tournament.config.version}", ephemeral=True, delete_after=10)
				print(f"MATCH SCREENSHOT: {interaction.user.global_name} screenshot {screen.filename} game version {steg.game_version} does not match tournament {self.tournament.config.version}")
				continue
			stop = False
			for seed in self.match.seeding:
				if not seed.player.check_ch_name(steg.players[0].profile_name) and not seed.player.check_ch_name(steg.players[1].profile_name):
					print(f"MATCH SCREENSHOT: {interaction.user.global_name} screenshot {screen.filename} players do not match players for this match")
					await interaction.followup.send(f"Screenshot {screen.filename} does not match players for this match", ephemeral=True, delete_after=10)
					stop = True
					break
			if stop:
				continue
			try:
				rnd = await self.match.matchDb.rounds.aget(chart=playedChart)
			except MatchRound.DoesNotExist:
				continue
			if not rnd.screenshot:
				print(f"MATCH SCREENSHOT: {interaction.user.global_name} screenshot {screen.filename} accepted")
				screen.filename = f"{uuid.uuid1()}.png"
				await sync_to_async(rnd.screenshot.save)(screen.filename, open(tool.img_path, 'rb'))
				rnd.steg = steg
				await rnd.asave()
			else:
				print(f"MATCH SCREENSHOT: {interaction.user.global_name} screenshot {screen.filename} already submitted")
		done = True
		retRnds = []
		async for rnd in MatchRound.objects.select_related('picked', 'chart', 'winner', 'loser').all().filter(match=self.match.matchDb):
			retRnds.append(rnd)
			if not rnd.steg:
				done = False
		self.match.rounds = retRnds
		if done:
			await self.match.finishMatch(interaction)
		else:
			await self.match.showTool(interaction)

	async def submitBtn(self, interaction: discord.Interaction):
		self.match.matchDb.winner = self.match.rounds[-1].winner
		self.match.matchDb.loser = self.match.rounds[-1].loser
		self.match.matchDb.ended_on = timezone.now()
		self.match.matchDb.complete = True
		await self.match.matchDb.asave()
		await self.match.showTool(interaction)
