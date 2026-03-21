import discord, uuid
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from asgiref.sync import sync_to_async

from corpoch import settings
from corpoch.models import Tournament, Chart, Match, MatchRound, Bracket, Group, GroupSeed, TournamentPlayer, MatchRound, MatchBan
from corpoch.dbot.models import CHEmoji
from corpoch.dbot.view.reftool import DiscordMatchView
from corpoch.types import TB_RULESETS, PICK_RULESETS, BAN_RULESETS

#This class is being written with the assumption of official tournament matches - exhibition can be made to extend this with custom logging/rules
class DiscordMatch():
	def __init__(self, bot, message=None, uuid=None):
		self.bot = bot
		self.msg = message
		self.guild = message.guild if message else None
		self.referee = message.user if hasattr(message, 'user') else None
		self.channel = message.channel if hasattr(message, 'channel') else None
		self.tourney = None
		self.bracket = None
		self.group = None
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
			self.referee = await self.guild.fetch_member(self.matchDb.referee)
			for seed in self.seeding:
				self.seeding_discord.append(await self.guild.fetch_member(seed.player.user))
			if not await self.isFinished() and len(self.bans) > 0 and (len(self.rounds) == 0 or self.rounds[-1].winner):
				await self.add_round()
		try:
			self.tourney = await Tournament.objects.select_related().aget(guild=self.msg.guild.id, active=True)
		except Tournament.DoesNotExist:
			await self.msg.respond("No active tourney - running exhibition mode not supported now", ephemeral=True)
			return

		try:
			self.bracket = await Bracket.objects.select_related("ruleset").aget(score_log=self.msg.channel.id)
		except Bracket.DoesNotExist: 
			await self.msg.respond("Channel is not a score log channel - please use this command in a match reporting channel.", ephemeral=True)
			return

		if isinstance(self.msg, discord.ApplicationContext):
			await self.msg.respond("Setting up")
		else:
			await self.showTool(self.msg)

	@sync_to_async
	def complete_match(self):
		self.matchDb.finished = True
		self.matchDb.save()

	async def finishMatch(self, interaction):
		print(f"Finishing match {self.matchDb.id}")
		await self.complete_match()
		embeds = [await self.genMatchEmbed()]
		shared_url = f"https://{settings.BASE_URL}/gallery/"
		async for rnd in self.matchDb.rounds.select_related():
			embed = discord.Embed(url=shared_url)
			embed.set_image(url=f"https://{settings.BASE_URL}{settings.MEDIA_URL}{rnd.screenshot}")
			embeds.append(embed)
		await interaction.edit(embeds=embeds[:10], view=None)

	@sync_to_async
	def load_match(self):
		self.matchDb = Match.objects.select_related().get(id=self.matchDb)
		self.channel = self.bot.get_channel(self.matchDb.channel)
		self.guild = self.channel.guild
		self.group = self.matchDb.group
		self.bracket = self.matchDb.group.bracket
		self.bracket.ruleset = self.bracket.ruleset
		self.bracket.tournament = self.bracket.tournament
		self.bracket.tournament.config = self.bracket.tournament.config
		self.players = self.matchDb.players
		self.seeding = list(self.matchDb.players.select_related('group', 'player').all())
		self.bans = list(self.matchDb.bans.select_related('chart', 'player').all())
		self.rounds = list(self.matchDb.rounds.select_related('chart', 'picked', 'winner', 'loser').all())
		self.chart = self.rounds[-1].chart if len(self.rounds) > 0 else None
		print(f"Reattached to on-going match {self.matchDb}")

	@sync_to_async
	def save_match(self):
		if self.group:
			self.matchDb.group = self.group
			self.matchDb.players.set(self.seeding)
			self.matchDb.message = self.msg.id if self.msg else None
			self.matchDb.channel = self.channel.id
			self.matchDb.referee = self.referee.id
			self.matchDb.save()
			self.bracket.tournament = self.bracket.tournament
			self.bracket.tournament.config = self.bracket.tournament.config

	async def showTool(self, interaction):
		is_message = isinstance(interaction, discord.Message)
		is_ctx = hasattr(interaction, 'interaction') and hasattr(interaction, 'command')

		if is_message:
			self.msg = interaction
		elif is_ctx:
			if not interaction.interaction.response.is_done():
				await interaction.defer()
			self.msg = await interaction.interaction.original_response()
		else:
			if not interaction.response.is_done():
				await interaction.response.defer()
			self.msg = interaction.message

		await self.save_match()
		view = DiscordMatchView(self)
		await view.init()
		embeds = [await self.genMatchEmbed()]
		if self.matchDb and self.matchDb.complete:
			embeds.append(await self.genScreenEmbed())

		if is_message:
			await interaction.edit(embeds=embeds, content=None, view=view)
		elif is_ctx:
			await interaction.interaction.edit_original_response(embeds=embeds, content=None, view=view)
		else:
			await interaction.edit_original_response(embeds=embeds, content=None, view=view)

	@property
	def setlist(self) -> list:
		if self.bracket:
			return self.bracket.setlist
		else:
			return None

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
			if self.matchDb.defer and self.bracket.ruleset.pick_ruleset.ban_ruleset == "deferboth":
				picked = self.seeding[1].player
			else:
				picked = self.seeding[0].player
		elif len(self.rounds) + 1 == self.bracket.ruleset.num_rounds and self.bracket.ruleset.tb_ruleset == 'refdecide':
			picked = None
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
		if not self._is_finished:
			self.rounds.append(MatchRound(num=len(self.rounds) + 1, match=self.matchDb, picked=picked))

	@sync_to_async
	def getScore(self) -> list:
		return self._score

	@sync_to_async
	def isFinished(self) -> bool:
		return self._is_finished

	@sync_to_async
	def isTieBreaker(self):
		if self._score[0] == self.bracket.ruleset.wins_needed - 1 and self._score[1] == self.bracket.ruleset.wins_needed - 1:
			return True
		else:
			return False

	async def genScreenEmbed(self):
		embed = discord.Embed(colour=0xFFFF66)
		embed.title = "Upload screenshots"
		embed.add_field(name="Directions", value="Players/Refs for this match - click upload screenshots and submit. List will update as valid ones are found.", inline=False)
		noneStr = ""
		validStr = ""
		for rnd in self.rounds:
			if rnd.steg:
				validStr += f"{rnd.chart.name}\n"
			else:
				noneStr += f"{rnd.chart.name}\n"
		embed.add_field(name="Valid Screenshots Submitted", value=validStr, inline=False)
		embed.add_field(name="Screenshots Missing", value=noneStr, inline=False)
		return embed

	async def genMatchEmbed(self):
		embed = discord.Embed(colour=0x3FFF33)
		embed.set_author(name=f"Ref: {self.referee.display_name}", icon_url=self.referee.display_avatar.url)

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
			embed.title = f"{self.tourney.short_name} - {self.bracket.name} - Group {self.group.name}\n{self.seeding[0].player.ch_name}({self.seeding[0].seed}) vs {self.seeding[1].player.ch_name} ({self.seeding[1].seed})"
			embed.add_field(name="Match VS", value=f"{self.seeding_discord[0].mention} vs {self.seeding_discord[1].mention}")
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
			elif self.bracket.ruleset.tb_ruleset == 'banpick' and len(self.rounds) == self.bracket.ruleset.num_rounds:
				outStr += f"***TIEBREAKER BAN***\n**{self.rounds[-2].winner.ch_name}** Bans"					
				if len(self.bans) < self.bracket.ruleset.total_bans + 1:
					outStr += " ---"
					embed.add_field(name="Bans", value=f"{outStr}\nSelect next ban", inline=False)
				else:
					outStr += f" {self.bans[-1]}"
					embed.add_field(name="Bans", value=outStr, inline=False)
			else:
				embed.add_field(name="Bans", value=outStr, inline=False)

		outStr = ""
		for i, rnd in enumerate(self.rounds):
			if i == self.bracket.ruleset.num_rounds - 1:
				outStr += "**TIEBREAKER**\n"

			outStr += f"{rnd.picked.ch_name if rnd.picked else '*Chat*'} picks {rnd.chart.tournament_name if rnd.chart else '---'}"
			if rnd.winner:
				outStr += f" - {rnd.winner.ch_name} wins!"
			outStr+= "\n"

		if (self.matchDb and self.matchDb.finished):
			outStr += f"\n**{self.rounds[-1].winner} WINS!**"
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
