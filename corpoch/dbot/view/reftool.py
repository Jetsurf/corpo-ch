import discord, uuid
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from asgiref.sync import sync_to_async

from corpoch.models import Tournament, Chart, TournamentMatchOngoing, MatchRound, TournamentBracket, BracketGroup, TournamentPlayer, TournamentMatchCompleted, GroupSeed, MatchRound, MatchBan
from corpoch.dbot.models import CHEmoji
from corpoch.dbot.view.helpers import get_chart_emoji

class MatchScreenModal(discord.ui.DesignerModal):
	def __init__(self, match):
		self.match = match
		self.screen = None
		file = discord.ui.Label("Match Screenshot Submission", discord.ui.FileUpload(max_values=len(self.match.rounds), required=True))
		super().__init__(discord.ui.TextDisplay("Screenshots"), file, title="Qualifier Screenshot")

	async def callback(self, interaction: discord.Interaction):
		self.screens = self.children[1].item.values
		await interaction.respond("Processing, wait for embed to update", ephemeral=True, delete_after=10)

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
			self.retOpts[chart.name] = chart
			opts.append(discord.SelectOption(label=str(chart), description=f"{chart.artist} - {chart.charter}", emoji=emoji))
		super().__init__(placeholder=f"{await sync_to_async(lambda: self.match.seeding[self.index].player.ch_name)()} Ban", max_values=1, options=opts, custom_id="ban_sel")

	async def callback(self, interaction: discord.Interaction):
		chart = self.retOpts[self.values[0]]
		seed = self.match.seeding[self.index]
		newBan = MatchBan(num=len(self.match.bans), player=seed, chart=chart, ongoing_match=self.match.matchDb)
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
		if len(self.match.rounds) > self.match.bracket.ruleset.num_rounds:
			charts = self.match.setlist.select_related('icon').filter(tiebreaker=True).exclude(id__in=bansDone)
		else:
			for rnd in self.match.rounds:
				chart = await sync_to_async(lambda: rnd.chart)()
				if chart:
					songOptsDone.append(chart.id)
			charts = self.match.setlist.select_related('icon').filter(tiebreaker=False).exclude(id__in=songOptsDone).exclude(id__in=bansDone)

		opts = []
		async for chart in charts:
			self.retOpts[chart.name] = chart
			emoji = await get_chart_emoji(self.match.bot, chart)
			opts.append(discord.SelectOption(label=chart.tournament_name, value=str(chart),description=f"{chart.artist} - {chart.charter}", emoji=emoji))
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
		for seed in self.match.seeding:
			self.retOpts[seed.player.ch_name] = seed
			opts.append(discord.SelectOption(label=f"{seed.player.ch_name} ({seed.seed})", value=seed.player.ch_name))
		super().__init__(placeholder="Round Winner", max_values=1, options=opts, custom_id="roundwin_sel", disabled=self.dis)

	async def callback(self, interaction: discord.Integration):
		winner = self.retOpts[self.values[0]]
		if winner == self.match.seeding[0]:
			self.round.loser = self.match.seeding[1].player
		else:
			self.round.loser = self.match.seeding[0].player
		self.round.winner = winner.player
		print(f"DEBUG: WINNER: {self.round.winner.ch_name} LOSER: {self.round.loser.ch_name}")
		await self.match.add_round()
		await self.match.showTool(interaction)

class BracketSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		self.retOpts = {}

	async def init(self):
		brackets = []
		async for bracket in self.match.tourney.brackets.all().filter(is_active=True):
			self.retOpts[bracket.name] = bracket
			brackets.append(discord.SelectOption(label=bracket.name))
		super().__init__(max_values=1, options=brackets, custom_id="bracket_sel")

	async def callback(self, interaction: discord.Integration):
		self.match.bracket = self.retOpts[self.values[0]]
		self.match.bracket.ruleset = await sync_to_async(lambda: self.match.bracket.ruleset)()
		self.match.setlist = self.match.bracket.setlist
		await self.match.showTool(interaction)

class GroupSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		self.retOpts = {}

	async def init(self):
		groups = []
		async for group in self.match.bracket.groups.all():
			self.retOpts[group.name] = group
			groups.append(discord.SelectOption(label=group.name))
		super().__init__(max_values=1, options=groups, custom_id="group_sel")

	async def callback(self, interaction: discord.Integration):
		self.match.group = self.retOpts[self.values[0]]
		self.match.matchDb = TournamentMatchOngoing(id=uuid.uuid1(), group=self.match.group)
		await self.match.matchDb.asave()
		await self.match.showTool(interaction)

class PlayerSelect(discord.ui.Select):
	def __init__(self, match, custom_id):
		self.match = match
		self.cid = custom_id
		self.retOpts = {}

	async def init(self):
		dis = True
		#I feel like this can come down, but not sure what's best
		if 'player1' in self.cid:
			if self.match.bracket.ruleset.num_players == 2:
				placeholder = "High Seed"
			else:
				placeholder = "Player 1"

			if len(self.match.seeding) > 0:
				placeholder += f" - {self.match.seeding[0].player.ch_name}"
			if len(self.match.seeding) == 0:
				dis = False

		elif 'player2' in self.cid:
			if self.match.bracket.ruleset.num_players == 2:
				placeholder = "Low Seed"
			else:
				placeholder = "Player 2"

			if len(self.match.seeding) > 1:
				placeholder += f" - {self.match.players[1].player.ch_name}"
			if len(self.match.seeding) == 1:
				dis = False
		elif 'player3' in self.cid:
			placeholder = "Player 3"
			if len(self.match.players) > 2:
				placeholder += f" - {self.match.players[2].ch_name}"
			if len(self.match.players) == 2:
				dis = False
		elif 'player4' in self.cid:
			placeholder = "Player 4"
			if len(self.match.players) > 3:
				placeholder += f" - {self.match.players[3].ch_name}"
			if len(self.match.players) == 3:
				dis = False
		id_list = []
		for seed in self.match.seeding:
			id_list.append(seed.id)

		seeding = []
		async for seed in self.match.group.seeding.select_related('player').all().exclude(id__in=id_list):
			if seed.player.is_active:
				self.retOpts[seed.player.ch_name] = seed
				seeding.append(discord.SelectOption(label=str(seed.player)))
		super().__init__(placeholder=placeholder, max_values=1,	options=seeding, custom_id=self.cid, disabled=dis)

	async def callback(self, interaction: discord.Interaction):
		seed = self.retOpts[self.values[0]]
		self.match.seeding.append(seed)
		self.match.seeding = sorted(self.match.seeding, key=lambda x: x.seed)
		self.match.seeding_discord.append(await self.match.guild.fetch_member(seed.player.user))
		await self.match.showTool(interaction)

class DiscordMatchView(discord.ui.View):
	def __init__(self, match):
		super().__init__(timeout = None)
		self.match = match
		self.ref = match.ref

		cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancelBtn")
		cancel.callback = self.cancelBtn
		self.add_item(cancel)

		self.back = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="backBtn")
		self.back.callback = self.backBtn

		self.plyin = discord.ui.Button(label="Allow player input", style=discord.ButtonStyle.secondary, custom_id="plyinBtn")
		self.plyin.callback = self.plyinBtn # Future idea

		self.upload = discord.ui.Button(label="Upload Screenshots", style=discord.ButtonStyle.secondary, custom_id="uploadBtn")
		self.upload.callback = self.uploadBtn

		self.submit = discord.ui.Button(label='Submit Match', style=discord.ButtonStyle.green, custom_id="submitBtn")
		self.submit.callback = self.submitBtn
		self.submit.disabled = True

	async def init(self):
		if self.match.matchDb and self.match.matchDb.finished:
			self.add_item(self.submit)
		elif not self.match.bracket:
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
			for i in range(self.match.bracket.ruleset.num_players):
				sel = PlayerSelect(self.match, f"player{i+1}_sel")
				await sel.init()
				self.add_item(sel)
		elif len(self.match.bans) < self.match.bracket.ruleset.total_bans:
			self.add_item(self.back)
			sel = BanSelect(self.match)
			await sel.init()
			self.add_item(sel)
		else:
			self.add_item(self.back)
			self.add_item(self.submit)
			if len(self.match.rounds) == 0:
				await self.match.add_round()

			wins = await self.match.getScore()
			print(f"DEBUG: WINS: {wins} - NEEDED: {self.match.bracket.ruleset.wins_needed}")
			if wins[0] < self.match.bracket.ruleset.wins_needed  and wins[1] < self.match.bracket.ruleset.wins_needed:
				sngDis = True if self.match.rounds[-1].chart else False
				sngSel = SongRoundSelect(self.match, sngDis)
				plyDis = True if not self.match.rounds[-1].chart else False
				plySel = PlayerRoundSelect(self.match, plyDis)
				await sngSel.init()
				await plySel.init()
				self.add_item(sngSel)
				self.add_item(plySel)
			elif wins[0] == (self.match.bracket.ruleset.wins_needed  - 1) and wins[1] == (self.match.bracket.ruleset.wins_needed - 1):
				pass #TB
			elif wins[0] == self.match.bracket.ruleset.wins_needed or wins[1] == self.match.bracket.ruleset.wins_needed:
				self.submit.disabled = False

	async def interaction_check(self, interaction: discord.Interaction):
		if self.match.matchDb.finished:
			async for seed in self.matchDb.match_players.select_related('player'):
				if seed.player.user == interaction.ctx.user.id:
					return True
		elif not self.match.matchDb.finished and interaction.user.id == self.match.ref.id:
			return True
		else:
			await interaction.response.send_message("You are not the ref for this match", ephemeral=True, delete_after=10)
			return False

	async def plyinBtn(self, interaction: discord.Interaction):
		pass

	async def backBtn(self, interaction: discord.Interaction):
		if len(self.match.rounds) > 0:
			rnd = self.match.rounds.pop()
			await rnd.adelete()
		elif len(self.match.bans) > 0:
			ban = self.match.bans.pop()
			await ban.adelete()
		elif len(self.match.seeding) > 0:
			seed = self.match.seeding.pop()
		elif self.match.group:
			await self.match.matchDb.adelete()
			self.match.group = None
		elif self.match.bracket:
			self.match.bracket = None

		await self.match.showTool(interaction)

	async def cancelBtn(self, interaction: discord.Interaction):
		if self.match.confirmCancel:
			await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=5)
			await self.match.matchDb.adelete()
			self.stop()
		else:
			self.match.confirmCancel = True
			await interaction.response.send_message(content="Are you sure you want to cancel? Click cancel again to confirm", ephemeral=True, delete_after=10)

	async def uploadBtn(self, interaction: discord.Interaction):
		modal = MatchScreenModal(self.match)
		await interaction.response.send_modal(modal)
		await modal.wait()

	async def submitBtn(self, interaction: discord.Interaction):
		self.matchDb.finished = True
		await self.matchDb.save()
		await self.match.showTool()