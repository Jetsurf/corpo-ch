import discord, uuid
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

from corpoch import settings
from corpoch.models import Tournament, Chart, Match, MatchRound, Bracket, Group, GroupSeed, TournamentPlayer, MatchRound, MatchBan, DiscordUser
from corpoch.dbot.models import CHEmoji, Channels
from corpoch.dbot.view.reftool import DiscordMatchView
from corpoch.types import TB_RULESETS, PICK_RULESETS, BAN_RULESETS, CHART_CATEGORIES

class DiscordMatch():
	def __init__(self, bot, message=None, uuid=None, exhibition=False):
		self.bot = bot
		self.msg = message
		self.guild = message.guild if message else None
		self.referee = message.user if hasattr(message, 'user') else None
		self.channel = message.channel if hasattr(message, 'channel') else None
		self.tourney = None
		self.bracket = None
		self.group = None
		self.seeding = []
		self.bans = []
		self.rounds = []
		self.matchDb = uuid
		self.exhibition = exhibition
		self.confirm_cancel = False
		self.player_input = False
		self.picking_player = None

	async def init(self) -> bool:
		if self.matchDb:
			self.load_match()
			#Finish loading async
			self.msg = await self.channel.fetch_message(self.matchDb.message)
			self.referee = await self.guild.fetch_member(self.matchDb.referee.id)
			if not self.complete and len(self.bans) == self.ruleset.total_bans and (len(self.rounds) == 0 or self.rounds[-1].winner):
				self.add_round()
		try:
			self.tourney = await Tournament.objects.select_related().aget(guild=self.msg.guild.id, active=True)
		except Tournament.DoesNotExist:
			await self.msg.respond("No active tourney - running exhibition mode not supported now", ephemeral=True)
			return False

		ref_role = self.referee.get_role(self.tourney.config.ref_role.id)
		if not ref_role and not self.referee.guild_permissions.administrator:
			await self.msg.respond("You are not a ref for this tournament!", ephemeral=False)
			return False
		try:
			self.bracket = await Bracket.objects.select_related("ruleset").aget(score_log__id=self.msg.channel.id, is_active=True)
		except Bracket.DoesNotExist: 
			await self.msg.respond("Channel is not a score log channel or no brackets are currently active.", ephemeral=True)
			return False

		if isinstance(self.msg, discord.ApplicationContext):
			await self.msg.respond("Setting up")
			return True
		else:
			await self.showTool(self.msg)
			return True

	async def finishMatch(self, interaction):
		print(f"Finishing match {self.id}")
		self.matchDb.finished = True
		await self.matchDb.asave()
		embeds = [await self.genMatchEmbed()]
		shared_url = f"https://{settings.BASE_URL}/gallery/"
		async for rnd in self.matchDb.rounds.select_related():
			embed = discord.Embed(url=shared_url)
			embed.set_image(url=f"https://{settings.BASE_URL}{settings.MEDIA_URL}{rnd.screenshot}")
			embeds.append(embed)
		await interaction.edit(embeds=embeds[:10], view=None)
		self.bot.matches.pop(self.id)

	async def showTool(self, interaction=None):
		self.picking_player = None
		is_message = isinstance(interaction, discord.Message)
		is_ctx = hasattr(interaction, 'interaction') and hasattr(interaction, 'command')

		if interaction:
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
			self.save_match()
		else:
			interaction = self.msg #Live reload
			is_message = True
			self.load_match()
		
		view = DiscordMatchView(self)
		await view.init()
		embeds = [await self.genMatchEmbed()]
		if self.matchDb and self.complete:
			embeds.append(await self.genScreenEmbed())

		if is_message:
			await interaction.edit(embeds=embeds, content=None, view=view)
		elif is_ctx:
			await interaction.interaction.edit_original_response(embeds=embeds, content=None, view=view)
		else:
			await interaction.edit_original_response(embeds=embeds, content=None, view=view)

	def load_match(self):
		if isinstance(self.matchDb, str):
			self.matchDb = Match.objects.select_related().get(id=self.matchDb)
		self.channel = self.bot.get_channel(self.matchDb.channel.id)
		self.guild = self.channel.guild
		self.group = self.matchDb.group
		self.bracket = self.matchDb.group.bracket
		self.players = self.matchDb.players
		self.seeding = list(self.matchDb.players.select_related('group', 'player').all())
		self.bans = list(self.matchDb.bans.select_related('chart', 'player').all())
		self.rounds = list(self.matchDb.rounds.select_related('chart', 'picked', 'winner', 'loser').all())
		print(f"Reattached to on-going match {self.matchDb}")

	def save_match(self):
		if self.group:
			self.bot.matches[self.id] = self
			self.matchDb.group = self.group
			self.matchDb.players.set(self.seeding)
			self.matchDb.message = self.msg.id if self.msg else None
			self.matchDb.channel = Channels.objects.get(id=self.channel.id)
			self.matchDb.referee = DiscordUser.objects.get(id=self.referee.id)
			self.matchDb.save()

	def add_round(self):
		chart = None
		if len(self.rounds) == 0:
			if self.defer and self.ruleset.ban_ruleset == "deferboth":
				picked = self.seeding[1].player
			else:
				picked = self.seeding[0].player
		elif self.tiebreaker and self.ruleset.tb_ruleset == 'refdecide':
			picked = None
		elif self.tiebreaker and self.ruleset.tb_ruleset == 'csc':
			fret, strum = 0, 0
			for rnd in self.rounds:
				if rnd.chart.category == "fret":
					fret += 1
				elif rnd.chart.category == "strum":
					strum += 1

			picked = None
			if strum < fret:
				chart = Chart.objects.get(category=CHART_CATEGORIES[3][0], tiebreaker=True)
			elif fret < strum:
				chart = Chart.objects.get(category=CHART_CATEGORIES[2][0], tiebreaker=True)
			else:
				chart = Chart.objects.get(category=CHART_CATEGORIES[1][0], tiebreaker=True)
		elif self.ruleset.pick_ruleset == "loserpicks":
			picked = self.rounds[-1].loser
		else:
			prevPicked = self.rounds[-1].loser
			if self.seeding[0].player == prevPicked:
				picked = self.seeding[0].player
			else:
				picked = self.seeding[1].player

		if len(self.rounds) > 0:
			self.rounds[-1].save()
		if not self.finished:
			self.rounds.append(MatchRound(num=len(self.rounds) + 1, match=self.matchDb, picked=picked, chart=chart))

	def format_bans_player(self, seed, bans):
		outStr = f"**{seed.player_ch_name} Bans**\n"
		for i in range(0, self.ruleset.num_bans):
			try:
				outStr += f"{bans[i]}\n"
			except IndexError:
				outStr += "--\n"
		return outStr

	@property
	def formatted_bans(self):
		bans1 = self.matchDb.high_seed_bans if not self.defer else self.matchDb.low_seed_bans
		bans2 = self.matchDb.low_seed_bans if not self.defer else self.matchDb.high_seed_bans
		ply1 = self.matchDb.high_seed if not self.defer else self.matchDb.low_seed
		ply2 = self.matchDb.low_seed if not self.defer else self.matchDb.high_seed
		bantb = None
		if len(bans1) > self.ruleset.num_bans:
			bantb = bans1.pop()
		elif len(bans2) > self.ruleset.num_bans:
			bantb = bans2.pop()
		outStr = self.format_bans_player(ply1, bans1)
		outStr += self.format_bans_player(ply2, bans2)
		if bantb:
			outStr += f"***TIEBREAKER BAN***\n{bantb.player.player_ch_name} bans {bantb.chart.tournament_name}"
		return outStr

	@property
	def formatted_rounds(self):
		outStr = ""
		for i, rnd in enumerate(self.rounds):
			if i == self.ruleset.num_rounds - 1:
				outStr += "**TIEBREAKER**\n"

			outStr += f"{('`' + rnd.picked.ch_name + '` picks ') if rnd.picked else 'Played Chart: '}{rnd.chart.tournament_name if rnd.chart else '---'}"
			if rnd.winner:
				outStr += f" - `{rnd.winner}` wins!"
			outStr+= "\n"
		if (self.matchDb and self.matchDb.finished):
			outStr += f"\n**`{self.rounds[-1].winner}` WINS!**"
		return outStr

	def remove_round(self):
		rnd = self.rounds.pop()
		if rnd.id:
			rnd.delete()

	def remove_ban(self):
		ban = self.bans.pop()
		if ban.id:
			ban.delete()

	@property
	def chart(self):
		return self.rounds[-1].chart if len(self.rounds) > 0 else None

	@property
	def complete(self) -> bool:
		if isinstance(self.matchDb, Match):
			return self.matchDb.complete
		else:
			return False

	@property
	def defer(self):
		if self.matchDb:
			return self.matchDb.defer
		else:
			return False

	@property
	def finished(self) -> bool:
		if not self.matchDb:
			return False
		if self.score[0] == self.ruleset.wins_needed or self.score[1] == self.ruleset.wins_needed:
			return True
		else:
			return False

	@property
	def ruleset(self):
		if self.bracket:
			return self.bracket.ruleset
		else:
			return None

	@property
	def setlist(self) -> list:
		if self.bracket:
			return self.bracket.setlist
		else:
			return None

	@property
	def score(self) -> list:
		wins = [0, 0]
		for rnd in self.rounds:
			if rnd.winner == self.seeding[0].player:
				wins[0] += 1
			elif rnd.winner:
				wins[1] += 1
		return wins

	@property
	def tiebreaker(self) -> bool:
		if self.score[0] == self.ruleset.wins_needed - 1 and self.score[1] == self.ruleset.wins_needed - 1:
			return True
		else:
			return False

	@property
	def id(self):
		if self.matchDb:
			return self.matchDb.id
		else:
			return None

	async def genScreenEmbed(self):
		embed = discord.Embed(colour=0xFFFF66)
		embed.title = "Upload screenshots"
		embed.add_field(name="Directions", value="Players/Refs for this match - click upload screenshots and submit. List will update as valid ones are found.", inline=False)
		noneStr = ""
		validStr = ""
		for rnd in self.rounds:
			if rnd.steg and len(rnd.steg.players) > 0:
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
			embed.title = f"{self.bracket.name}"
			embed.add_field(name="Group Select", value=f"Select which group the match is for", inline=False)
		elif len(self.seeding) < self.ruleset.num_players:
			embed.title = f"{self.group}"
			embed.add_field(name="Player Select", value=f"Select which players the match is for", inline=False)
		else:
			embed.title = f"{self.group}\n{self.seeding[0]} vs {self.seeding[1]}"
			embed.add_field(name="Match VS", value=f"{self.seeding[0].mention} vs {self.seeding[1].mention}")
			embed.add_field(name="Score", value=f"{self.score[0]} - {self.score[1]}", inline=False)
			if self.defer:
				embed.add_field(name="Deferral", value=f"{self.matchDb.high_seed.player.ch_name} has deferred.")
			if len(self.bans) < self.ruleset.num_bans:
				embed.add_field(name="Bans", value=f"{self.formatted_bans}\nSelect next ban", inline=False)
			elif self.ruleset.tb_ruleset == 'banpick' and len(self.rounds) == self.ruleset.num_rounds:
				if len(self.bans) < self.ruleset.total_bans + 1:
					embed.add_field(name="Bans", value=f"{self.formatted_bans}\nSelect next ban", inline=False)
				else:
					embed.add_field(name="Bans", value=self.formatted_bans, inline=False)
			else:
				embed.add_field(name="Bans", value=self.formatted_bans, inline=False)
		embed.add_field(name="Rounds", value=self.formatted_rounds, inline=False)
		if self.matchDb:
			embed.set_footer(text=f"Match ID: {self.id}")
		return embed

class TourneyCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	tourney = discord.SlashCommandGroup('tourney','Clone Hero Tournament Commands')

	#@tourney.command(name="exhibition", description="Reftool for Exhibition Matches", integration_types={discord.IntegrationType.guild_install})
	#async def discordExhibMatchCmd(self, ctx):
	#	pass

	@tourney.command(name='match',description='Match reporting done within discord', integration_types={discord.IntegrationType.guild_install})
	async def discordMatchCmd(self, ctx):
		match = DiscordMatch(self.bot, message=ctx)
		if await match.init():
			await match.showTool(ctx)

def setup(bot):
	bot.add_cog(TourneyCmds(bot))
