import discord, uuid, json, re
from itertools import chain

from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from django.utils import timezone

from corpoch.dbot import settings
from corpoch.providers import CHStegTool
from corpoch.types import StegScreenshot, TB_RULESETS, PICK_RULESETS, BAN_RULESETS
from corpoch.models import Tournament, Chart, GroupSeed, Match, MatchRound, TournamentPlayer, MatchRound, MatchBan
from corpoch.dbot.models import CHEmoji
from corpoch.dbot.view.helpers import get_chart_emoji

class MatchScreenModal(discord.ui.DesignerModal):
	def __init__(self, match):
		self.match = match
		self.screens = None
		file = discord.ui.Label("Match Screenshot Submission", discord.ui.FileUpload(max_values=len(self.match.rounds), required=True))
		super().__init__(discord.ui.TextDisplay("Screenshots"), file, title="Match Screenshots", custom_id="screenModal")

	async def callback(self, interaction: discord.Interaction):
		await interaction.respond("Processing, wait for embed to update", ephemeral=True, delete_after=10)
		self.screens = self.children[1].item.values
		self.stop()

class SeedSearchModal(discord.ui.DesignerModal):
	def __init__(self, match):
		self.match = match
		super().__init__(discord.ui.TextDisplay("Search for players.\nAccepts partial case-insensitive discord names."), title="Search Players", custom_id="searchModal")
		self.add_item(discord.ui.Label("Player 1 Search", discord.ui.InputText(placeholder="Discord Name", required=True, style=discord.InputTextStyle.short)))
		self.add_item(discord.ui.Label("Player 2 Search", discord.ui.InputText(placeholder="Discord Name", required=True, style=discord.InputTextStyle.short)))

	async def callback(self, interaction: discord.Interaction):
		query1 = self.match.group.seeding.select_related('player').all().filter(player__is_active=True, eliminated=False, player__name__icontains=self.children[1].item.value)
		query2 = self.match.group.seeding.select_related('player').all().filter(player__is_active=True, eliminated=False, player__name__icontains=self.children[2].item.value)

		if len(query1) < 1:
			await interaction.respond(f"Search `{self.children[1].item.value}` found no results.", ephemeral=True, delete_after=10)
		elif len(query2) < 1:
			await interaction.respond(f"Search `{self.children[2].item.value}` found no results.", ephemeral=True, delete_after=10)
		else:
			retList = list(chain(query1, query2))
			if len(retList) > 25:
				await interaction.respond("Search(es) too broad, please narrow your search.", ephemeral=True, delete_after=10)
			else:
				await interaction.response.defer(invisible=True)
				self.match.seeding_search = retList

		self.stop()

class BanSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		self.retOpts = {}

	async def init(self):
		opts = []
		async for chart in self.match.setlist_remaining:
			emoji = await get_chart_emoji(self.match.bot, chart)
			self.retOpts[chart.md5] = chart
			opts.append(discord.SelectOption(label=str(chart.tournament_name), description=f"{chart.artist} - {chart.charter}", emoji=emoji, value=chart.md5))

		super().__init__(placeholder=f"{self.match.picking_player.ch_name} Ban", max_values=1, options=opts, custom_id="ban_sel")

	async def callback(self, interaction: discord.Interaction):
		chart = self.retOpts[self.values[0]]
		self.match.add_ban(self.match.picking_player, chart)
		await self.match.showTool(interaction)

class SongRoundSelect(discord.ui.Select):
	def __init__(self, match, disabled):
		self.match = match
		self.round = self.match.current_round
		self.dis = disabled
		self.retOpts = {}

	async def init(self):
		picked = self.match.picking_player
		if picked:
			selStr = f"{picked.ch_name} Picks"
		else:
			selStr = "Pick Song"

		if self.round.chart:
			selStr += f" - {self.round.chart.tournament_name}"

		opts = []
		async for chart in self.match.setlist_remaining:
			self.retOpts[chart.md5] = chart
			emoji = await get_chart_emoji(self.match.bot, chart)
			opts.append(discord.SelectOption(label=chart.tournament_name, value=chart.md5, description=f"{chart.artist} - {chart.charter}", emoji=emoji))
		super().__init__(placeholder=selStr, max_values=1, options=opts, custom_id="roundsong_sel", disabled=self.dis)

	async def callback(self, interaction: discord.Integration):
		self.round.chart = self.retOpts[self.values[0]]
		await self.round.asave()
		await self.match.showTool(interaction)

class PlayerRoundSelect(discord.ui.Select):
	def __init__(self, match, disabled):
		self.match = match
		self.round = self.match.current_round
		self.dis = disabled
		self.retOpts = {}

	async def init(self):
		opts = []
		for seed in self.match.seeding:
			auuid = str(uuid.uuid1())
			self.retOpts[auuid] = seed
			opts.append(discord.SelectOption(label=f"{seed.player.ch_name} ({seed.seed})", value=auuid, description=f"@{seed.player.name}"))
		super().__init__(placeholder="Round Winner", max_values=1, options=opts, custom_id="roundwin_sel", disabled=self.dis)

	async def callback(self, interaction: discord.Integration):
		winner = self.retOpts[self.values[0]]
		if winner == self.match.seeding[0]:
			self.round.loser = self.match.seeding[1].player
		else:
			self.round.loser = self.match.seeding[0].player
		self.round.winner = winner.player
		await self.round.asave()
		if not self.match.finished and (not self.match.tiebreaker or not self.match.ruleset.bannable_tb):
			self.match.add_round()
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
		group = self.retOpts[self.values[0]]
		self.match.matchDb = Match(id=uuid.uuid1(), group=group)
		print(f"REF: {self.match.referee.global_name} starting match {self.match.id}")
		await self.match.showTool(interaction)

class PlayerSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		self.retOpts = {}

	async def init(self):
		seeding = []
		seeds = self.match.group.seeding.select_related('player').all().filter(player__is_active=True, eliminated=False)
		if len(seeds) > 25:
			seeds = self.match.seeding_search

		for seed in seeds:
			self.retOpts[str(seed.user.id)] = seed
			seeding.append(discord.SelectOption(label=str(seed), value=str(seed.user.id), description=f"@{seed.player.name}"))
		plys = self.match.ruleset.num_players
		super().__init__(placeholder="Players", min_values=plys, max_values=plys, options=seeding, custom_id="player_sel")

	async def callback(self, interaction: discord.Interaction):
		self.values.sort(key=lambda ply: self.retOpts[ply].seed)
		for ply in self.values:
			self.match.seeding_mgr.add(self.retOpts[ply])
		await self.match.showTool(interaction)

class DiscordMatchView(discord.ui.View):
	def __init__(self, match):
		super().__init__(timeout = None)
		self.match = match
		self.referee = match.referee
		self.current_round = match.current_round

		self.cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancelBtn")
		self.cancel.callback = self.cancelBtn

		self.back = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="backBtn")
		if len(self.match.seeding) == 0:
			self.back.disabled = True
		self.back.callback = self.backBtn

		self.defer = discord.ui.Button(label="Defer", style=discord.ButtonStyle.secondary, custom_id="deferBtn")
		self.defer.callback = self.deferBtn

		self.search = discord.ui.Button(label="Player Select", style=discord.ButtonStyle.secondary, custom_id="searchBtn")
		self.search.callback = self.searchBtn

		if self.match.player_input:
			label = "Player Input ✅"
		else:
			label = "Player input ❌"
		self.plyin = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id="plyinBtn")
		self.plyin.callback = self.plyinBtn # Future idea

		self.upload = discord.ui.Button(label="Upload Screenshots", style=discord.ButtonStyle.secondary, custom_id="uploadBtn")
		self.upload.callback = self.uploadBtn

		self.submit = discord.ui.Button(label='Submit Match', style=discord.ButtonStyle.green, custom_id="submitBtn")
		self.submit.callback = self.submitBtn
		self.submit.disabled = True

	async def setup_round_player_sels(self):
		sngDis = True if self.match.current_round.chart else False
		sngSel = SongRoundSelect(self.match, sngDis)
		plyDis = True if not self.match.current_round.chart else False
		plySel = PlayerRoundSelect(self.match, plyDis)
		await sngSel.init()
		await plySel.init()
		self.add_item(sngSel)
		self.add_item(plySel)

	async def init(self):
		if self.match.complete:
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
		elif len(self.match.seeding) < self.match.ruleset.num_players:
			self.add_item(self.back)
			if len(self.match.group.seeding.select_related('player').all().filter(eliminated=False, player__is_active=True)) > 25:
				self.add_item(self.search)
			if len(self.match.group.seeding.select_related('player').all().filter(eliminated=False, player__is_active=True)) <= 25 or len(self.match.seeding_search) > 1: 
				sel = PlayerSelect(self.match)
				await sel.init()
				self.add_item(sel)
		elif len(self.match.bans) < self.match.ruleset.total_bans:
			self.add_item(self.back)
			self.add_item(self.plyin)
			if 'defer' in self.match.ruleset.ban_ruleset and len(self.match.bans) == 0:
				self.add_item(self.defer)
			sel = BanSelect(self.match)
			await sel.init()
			self.add_item(sel)
		elif not self.match.complete:
			self.add_item(self.back)
			self.add_item(self.plyin)
			self.add_item(self.submit)
			if not self.match.finished and not self.match.tiebreaker:
				await self.setup_round_player_sels()
			elif not self.match.finished and self.match.tiebreaker:
				if self.match.ruleset.bannable_tb:
					if len(self.match.bans) == self.match.ruleset.total_bans:
						sel = BanSelect(self.match)
						await sel.init()
						self.add_item(sel)
					else:
						await self.setup_round_player_sels()
				elif self.match.ruleset.tb_ruleset == 'csc':
					sel = PlayerRoundSelect(self.match, False)
					await sel.init()
					self.add_item(sel)
				else:
					await self.setup_round_player_sels()
			else:
				self.submit.disabled = False

	async def interaction_check(self, interaction: discord.Interaction):
		caller = interaction.custom_id
		if interaction.user in self.match.bot.owners:
			return True
		if interaction.user.id == self.match.referee.id:
			return True
		if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
			return True
		try:
			self.match.matchDb.players.get(player__user__id=interaction.user.id)
		except GroupSeed.DoesNotExist:
			await interaction.response.send_message("You are not the ref for, nor a player in this match!", ephemeral=True, delete_after=10)
			return False
		if self.match.complete:#If match is complete and player is part of match
			return True
		if self.match.player_input and (caller == "roundsong_sel" or caller == "ban_sel"):
			if self.match.picking_player and self.match.picking_player.user.id == interaction.user.id:
				return True
			else:
				await interaction.response.send_message("Not your turn to pick!", ephemeral=True, delete_after=10)
				return False
		elif not self.match.player_input:
			await interaction.response.send_message("Player input is disabled!", ephemeral=True, delete_after=10)
			return False
		else: #match.player_input is on but is from a caller object that isn't allowed for player input
			await interaction.response.send_message("Selector/Button not allowed for player input!!", ephemeral=True, delete_after=10)
			return False

	async def plyinBtn(self, interaction: discord.Interaction):
		self.match.player_input = not self.match.player_input
		await self.match.showTool(interaction)

	async def backBtn(self, interaction: discord.Interaction):
		if self.match.rounds.count() > 0:
			if self.current_round.is_tiebreaker:
				if self.current_round.winner:
					self.current_round.winner = None
					self.current_round.loser = None
				elif self.match.ruleset.pickable_tb and self.current_round.chart:
					self.current_round.chart = None
				else:
					self.current_round = self.match.remove_round()
					if self.match.ruleset.bannable_tb:
						self.match.remove_ban()
					else:
						self.current_round.winner = None
			elif self.current_round.winner:
				self.current_round.winner = None
				self.current_round.loser = None
			elif self.current_round.chart and (not self.match.tiebreaker or self.match.ruleset.pickable_tb):
				self.current_round.chart = None
			else:
				self.current_round = self.match.remove_round()
				if self.current_round:
					self.current_round.winner = None
			if self.match.rounds.count() > 0:
				await self.current_round.asave()
			else: #If we removed the last round, also remove a ban
				self.match.remove_ban()
		elif self.match.rounds.count() == 0 and self.match.bans.count() > 0:
			self.match.remove_ban()
		elif self.match.seeding.count() > 0 and self.match.bans.count() == 0:
			self.match.seeding_mgr.clear()

		await self.match.showTool(interaction)

	async def cancelBtn(self, interaction: discord.Interaction):
		if self.match.confirm_cancel:
			await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=10)
			if self.match.matchDb:
				await self.match.matchDb.adelete()
			self.stop()
		else:
			self.match.confirm_cancel = True
			await interaction.response.send_message(content="Are you sure you want to cancel? Click cancel again to confirm", ephemeral=True, delete_after=10)

	async def deferBtn(self, interaction: discord.Interaction):
		self.match.matchDb.defer = not self.match.defer
		await self.match.showTool(interaction)

	async def searchBtn(self, interaction: discord.Interaction):
		modal = SeedSearchModal(self.match)
		await interaction.response.send_modal(modal)
		await modal.wait()
		await self.match.showTool(interaction)

	async def uploadBtn(self, interaction: discord.Interaction):
		modal = MatchScreenModal(self.match)
		await interaction.response.send_modal(modal)
		await modal.wait()
		for screen in modal.screens:
			tool = CHStegTool()
			try:
				steg = await tool.getStegInfo(screen)
				rnd = await MatchRound.objects.select_related('chart').aget(match__id=self.match.id, chart__md5=steg.checksum)
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
				rnd.screenshot.save(screen.filename, open(tool.img_path, 'rb'))
				rnd.steg = steg
				await rnd.asave()
			else:
				print(f"MATCH SCREENSHOT: {interaction.user.global_name} screenshot {screen.filename} already submitted")
		
		if self.match.rounds.filter(steg=None).count() == 0:
			await self.match.finishMatch(interaction)
		else :
			await self.match.showTool(interaction)

	async def submitBtn(self, interaction: discord.Interaction):
		self.match.matchDb.winner = self.match.current_round.winner
		self.match.matchDb.loser = self.match.current_round.loser
		self.match.matchDb.ended_on = timezone.now()
		self.match.matchDb.complete = True
		await self.match.showTool(interaction)
