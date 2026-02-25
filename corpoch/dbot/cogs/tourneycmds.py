import math
import uuid
import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from asgiref.sync import sync_to_async

from corpoch.models import Tournament, Chart, TournamentMatchOngoing, MatchRound, TournamentBracket, BracketGroup, TournamentPlayer, TournamentMatchCompleted, GroupSeed, MatchRound, MatchBan
from corpoch.dbot.models import CHEmoji

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
			try:
				icon = await CHEmoji.objects.select_related().aget(icon_id=chart.icon)
			except CHEmoji.DoesNotExist:
				icon = await CHEmoji.objects.select_related().aget(icon_id='ch')
			emoji = await self.match.bot.fetch_emoji(icon.id)
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
			selStr += f"{self.match.rounds[-1].loser.ch_name} Picks"
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
		if len(self.match.rounds) > self.match.bracket.ruleset.num_rounds / 2:
			charts = self.match.setlist.select_related('icon').filter(tiebreaker=True).exclude(id__in=bansDone)
		else:
			for rnd in self.match.rounds:
				if rnd.chart:
					songOptsDone.append(rnd.chart.id)
			charts = self.match.setlist.select_related('icon').filter(tiebreaker=False).exclude(id__in=songOptsDone).exclude(id__in=bansDone)

		opts = []
		async for chart in charts:
			self.retOpts[chart.name] = chart
			try:
				icon = await CHEmoji.objects.select_related().aget(icon_id=chart.icon)
			except CHEmoji.DoesNotExist:
				icon = await CHEmoji.objects.select_related().aget(icon_id='ch')
			emoji = await self.match.bot.fetch_emoji(icon.id)
			opts.append(discord.SelectOption(label=str(chart), description=f"{chart.artist} - {chart.charter}", emoji=emoji))
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
		async for bracket in self.match.tourney.brackets.all():
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

#This class is being written with the assumption of official tournament matches - exhibition can be made to extend this with custom logging/rules
class DiscordMatch():
	def __init__(self, bot, message=None, uuid=None):
		#Make it so if user is not a ref, self match where each player picks options is required
		self.bot = bot
		self.msg = message
		self.guild = message.guild if message else None
		self.ref = message.user if hasattr(message, 'user') else None
		self.channel = message.channel if hasattr(message, 'channel') else None
		self.tourney = None
		self.bracket = None
		self.group = None
		self.setlist = None
		self.seeding = []
		self.seeding_discord = []
		self.bans = []
		self.rounds = []
		self.matchDb = uuid
		self.confirmCancel = False
		#TODO - figure out how to allow exhibition matches(?)

	async def init(self):
		if self.matchDb:
			await self.load_match()
			#Finish loading async
			self.msg = await self.channel.fetch_message(self.matchDb.message)
			self.ref = await self.guild.fetch_member(self.matchDb.ref)
			for seed in self.seeding:
				self.seeding_discord.append(await self.guild.fetch_member(seed.player.user))
		try:
			self.tourney = await Tournament.objects.aget(guild=self.msg.guild.id, active=True)#Assuming single tourney for now
		except Tournament.DoesNotExist:
			await self.msg.respond("No active tourney - running exhibition mode not supported now", ephemeral=True)
			return
		if isinstance(self.msg, discord.ApplicationContext):#We're loading from DB - fetch everything async
			await self.msg.respond("Setting up")
		else:
			await self.showTool(self.msg)

	async def finishMatch(self, interaction):
		#Save match results to DB
		await interaction.edit(embeds=[self.genMatchEmbed()], content=None, view=None)		

	@sync_to_async
	def load_match(self):
		self.matchDb = TournamentMatchOngoing.objects.select_related().get(id=self.matchDb)
		self.channel = self.bot.get_channel(self.matchDb.channel)
		self.guild = self.channel.guild
		self.group = self.matchDb.group
		self.bracket = self.matchDb.group.bracket
		self.bracket.ruleset = self.bracket.ruleset
		self.setlist = self.matchDb.bracket.setlist
		self.match_players = self.matchDb.match_players
		#self.seeding = list(self.matchDb.group.seeding.select_related().all())
		self.seeding = list(self.matchDb.group.seeding.select_related().filter(id__in=self.matchDb.match_players.all().only('id')))
		self.bans = list(self.matchDb.matchban_bans.all())
		self.rounds = list(self.matchDb.ongoing_rounds.select_related().all())
		for rnd in self.rounds:
			print(f"TEST ROUNGS: {rnd}")
		self.chart = self.rounds[-1].chart if len(self.rounds) > 0 else None

		#load the objects
		for ban in self.bans:
			tmp = ban.chart
		for seed in self.seeding:
			tmp = seed.player
		for chart in self.setlist.all():
			tmp = chart
		for rnd in self.rounds:
			tmep = rnd

		print(f"Reattached to on-going match {self.matchDb}")
		
	@sync_to_async
	def save_match(self):
		if self.group:
			self.matchDb.group = self.group
			plyList = []
			#self.matchDb.seeding = self.seeding
			self.matchDb.match_players.set(self.seeding)
			#self.matchDb.ongoing_rounds.set(self.rounds)
			self.matchDb.message = self.msg.id if self.msg else None
			self.matchDb.channel = self.channel.id
			self.matchDb.ref = self.ref.id
			self.matchDb.bans = self.bans
			self.matchDb.save()

	async def showTool(self, interaction):
		if isinstance(interaction, discord.Message):
			self.msg = interaction
		else:
			self.msg = interaction.message

		await self.save_match()
		view = DiscordMatchView(self)
		await view.init()
		await interaction.edit(embeds=[await self.genMatchEmbed()], content=None, view=view)
		
	@sync_to_async
	def add_round(self):
		if len(self.rounds) == 0:
			picked = self.seeding[0].player
		elif self.bracket.ruleset.pick_ruleset == "loserpicks":
			picked = self.rounds[-1].loser
		else:
			prevPicked = self.rounds[-1].loser
			if self.seeding[0].player == prevPicked:
				picked = self.seeding[0].player
			else:
				picked = self.seeding[1].player

		if len(self.rounds) > 0:
			self.rounds[-1].save()
		self.rounds.append(MatchRound(num=len(self.rounds) + 1, ongoing_match=self.matchDb, picked=picked))

	async def genMatchEmbed(self):
		embed = discord.Embed(colour=0x3FFF33)
		embed.set_author(name=f"Ref: {self.ref.display_name}", icon_url=self.ref.avatar.url)

		if not self.bracket:
			embed.title = f"{self.tourney.short_name}"
			embed.add_field(name="Bracket Select", value=f"Select which bracket the match is for", inline=False)
		elif not self.group:
			embed.title = f"{self.tourney.short_name} - {self.bracket.name}"
			embed.add_field(name="Group Select", value=f"Select which group the match is for", inline=False)
		elif len(self.seeding) < self.bracket.ruleset.num_players:
			embed.title = f"{self.tourney.short_name} - {self.bracket.name} - Group {self.group.name}"
			embed.add_field(name="Player Select", value=f"Select which players the match is for", inline=False)
		else:
			embed.title = f"{self.tourney.short_name} - {self.bracket.name} - Group {self.group.name}\n{self.seeding_discord[0].mention}({self.seeding[0].seed}) vs {self.seeding_discord[1].mention} ({self.seeding[1].seed})"
			outStr = ""
			for i, seed in enumerate(self.seeding):
				outStr += f"**{seed.player.ch_name} Bans**\n"
				for j in range(0, self.bracket.ruleset.num_bans):
					try:
						outStr += f"{self.bans[j+i]}\n"
					except IndexError:
						outStr += "--\n"
			if len(self.bans) < self.bracket.ruleset.num_bans:
				embed.add_field(name="Bans", value=f"{outStr}\nSelect next ban", inline=False)
			else:
				embed.add_field(name="Bans", value=outStr, inline=False)
		
		if self.bans and len(self.bans) == self.bracket.ruleset.num_bans * self.bracket.ruleset.num_players:
			outStr = ""
			for i, rnd in enumerate(self.rounds):
				if i > self.bracket.ruleset.num_rounds:
					outStr += "**TIEBREAKER**"

				outStr += f"{rnd.picked.ch_name} picks {rnd.chart.tournament_name if rnd.chart else '---'}"
				if rnd.winner:
					outStr += f" - {rnd.winner.ch_name} wins!"
				outStr+= "\n"

			embed.add_field(name="Rounds", value=outStr, inline=False)
		if self.matchDb:
			embed.set_footer(text=f"Match ID: {self.matchDb.id}")
		return embed

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

		self.submit = discord.ui.Button(label='Submit Match', style=discord.ButtonStyle.green, custom_id="submitBtn")
		self.submit.callback = self.submitBtn
		self.submit.disabled = True

	async def init(self):
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
			for i in range(self.match.bracket.ruleset.num_players):
				sel = PlayerSelect(self.match, f"player{i+1}_sel")
				await sel.init()
				self.add_item(sel)
		elif len(self.match.bans) < (self.match.bracket.ruleset.num_bans * self.match.bracket.ruleset.num_players):
			self.add_item(self.back)
			sel = BanSelect(self.match)
			await sel.init()
			self.add_item(sel)
		else:
			self.add_item(self.back)
			self.add_item(self.submit)
			if len(self.match.rounds) == 0:
				await self.match.add_round()

			wins = await self.getScore()
			winsNeeded = int(math.floor(self.match.bracket.ruleset.num_rounds / 2))
			if wins[0] < winsNeeded and wins[1] < winsNeeded:
				sngDis = True if self.match.rounds[-1].chart else False
				sngSel = SongRoundSelect(self.match, sngDis)
				plyDis = True if not self.match.rounds[-1].chart else False
				plySel = PlayerRoundSelect(self.match, plyDis)
				await sngSel.init()
				await plySel.init()
				self.add_item(sngSel)
				self.add_item(plySel)

	@sync_to_async
	def getScore(self) -> list:
		wins = [0, 0] #Cleaner way?
		for rnd in self.match.rounds:
			if rnd.winner == self.match.seeding[0]:
				wins[0] += 1
			else:
				wins[1] += 1
		return wins

	async def interaction_check(self, interaction: discord.Interaction):
		if interaction.user.id == self.match.ref.id:
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
		await interaction.response.defer(invisible=True)
		await self.match.finishMatch(interaction)

class TourneyCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	tourney = discord.SlashCommandGroup('tourney','Clone Hero Tournament Commands')
	match = tourney.create_subgroup('match', 'Tourney Match Reporting Commands')

	@match.command(name='discord',description='Match reporting done within discord', integration_types={discord.IntegrationType.guild_install})
	async def discordMatchCmd(self, ctx):
		#TODO - Self Ref Match Check setup (DM user that didn't run the command to confirm?)
		#     - Can bypass above with having a "Ref" role assigned
		match = DiscordMatch(self.bot, message=ctx)
		await match.init()
		await match.showTool(ctx)

def setup(bot):
	bot.add_cog(TourneyCmds(bot))
