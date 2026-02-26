import discord, uuid
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from asgiref.sync import sync_to_async

from corpoch.models import Tournament, Chart, TournamentMatchOngoing, MatchRound, TournamentBracket, BracketGroup, TournamentPlayer, TournamentMatchCompleted, GroupSeed, MatchRound, MatchBan
from corpoch.dbot.models import CHEmoji
from corpoch.dbot.view.reftool import DiscordMatchView

#This class is being written with the assumption of official tournament matches - exhibition can be made to extend this with custom logging/rules
class DiscordMatch():
	def __init__(self, bot, message=None, uuid=None):
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

	async def init(self):
		if self.matchDb:
			await self.load_match()
			#Finish loading async
			self.msg = await self.channel.fetch_message(self.matchDb.message)
			self.ref = await self.guild.fetch_member(self.matchDb.ref)
			for seed in self.seeding:
				self.seeding_discord.append(await self.guild.fetch_member(seed.player.user))
			if not await self.isFinished() and (len(self.rounds) == 0 or self.rounds[-1].winner):
				await self.add_round()
		try:
			self.tourney = await Tournament.objects.aget(guild=self.msg.guild.id, active=True)
		except Tournament.DoesNotExist:
			await self.msg.respond("No active tourney - running exhibition mode not supported now", ephemeral=True)
			return
		if isinstance(self.msg, discord.ApplicationContext):
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
		self.seeding = list(self.matchDb.group.seeding.select_related('group', 'player').filter(id__in=self.matchDb.match_players.all().only('id')))
		self.bans = list(self.matchDb.matchban_bans.select_related('chart', 'player').all())
		self.rounds = list(self.matchDb.ongoing_rounds.select_related('chart', 'picked', 'winner', 'loser').all())
		self.chart = self.rounds[-1].chart if len(self.rounds) > 0 else None

		print(f"Reattached to on-going match {self.matchDb}")
		
	@sync_to_async
	def save_match(self):
		if self.group:
			self.matchDb.group = self.group
			plyList = []
			self.matchDb.match_players.set(self.seeding)
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

	@property
	def _score(self) -> list:
		wins = [0, 0] #Cleaner way?
		for rnd in self.rounds:
			if rnd.winner == self.seeding[0].player:
				wins[0] += 1
			elif rnd.winner:
				wins[1] += 1
		return wins

	@property
	def _is_finished(self) -> bool:
		wins = self._score
		if wins[0] == self.bracket.ruleset.wins_needed or wins[1] == self.bracket.ruleset.wins_needed:
			return True
		else:
			return False

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
		elif not self._is_finished:
			self.rounds.append(MatchRound(num=len(self.rounds) + 1, ongoing_match=self.matchDb, picked=picked))

	@sync_to_async
	def getScore(self) -> list:
		return self._score

	@sync_to_async
	def isFinished(self) -> bool:
		return self._is_finished

	async def genScreenEmbed(self):
		pass

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
		
		if self.bans and len(self.bans) == self.bracket.ruleset.total_bans:
			outStr = ""
			for i, rnd in enumerate(self.rounds):
				if i == self.bracket.ruleset.num_rounds:
					outStr += "**TIEBREAKER**"

				outStr += f"{rnd.picked.ch_name} picks {rnd.chart.tournament_name if rnd.chart else '---'}"
				if rnd.winner:
					outStr += f" - {rnd.winner.ch_name} wins!"
				outStr+= "\n"

			embed.add_field(name="Rounds", value=outStr, inline=False)
		if self.matchDb:
			embed.set_footer(text=f"Match ID: {self.matchDb.id}")
		return embed

class TourneyCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	tourney = discord.SlashCommandGroup('tourney','Clone Hero Tournament Commands')

	@tourney.command(name='match',description='Match reporting done within discord', integration_types={discord.IntegrationType.guild_install})
	async def discordMatchCmd(self, ctx):
		match = DiscordMatch(self.bot, message=ctx)
		await match.init()
		await match.showTool(ctx)

def setup(bot):
	bot.add_cog(TourneyCmds(bot))
