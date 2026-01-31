import math
import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from asgiref.sync import sync_to_async

from corpoch.models import Chart, Tournament, TournamentBracket, BracketGroup, TournamentPlayer, TournamentMatchOngoing, TournamentMatchCompleted

class RefToolModal(Modal):
	def __init__(self, *args, **kwargs):
		self.title="CSC Ref Tool Submission"
		super().__init__(*args, **kwargs)
		self.refToolInput = None
		self.add_item(InputText(label="Ref Tool Output", style=discord.InputTextStyle.long))

	async def callback(self, interaction: discord.Interaction):
		#need sanity checking first, but placeholder for now
		await interaction.response.send_message("Accepting your submission blindly for now!", ephemeral=True)
		self.refToolInput = self.children[0].value
		self.stop()

class BanSelect(discord.ui.Select):
	def __init__(self, match, custom_id):
		self.match = match
		self.usedSave = False

		if 'player1' in custom_id:
			if self.match.ban1:
				if self.match.savesEnabled and self.match.ban1['save']:
					placeholder = f"{self.match.player1.display_name} saves {self.match.ban1['name']}"
				else:
					placeholder = f"{self.match.player1.display_name} bans {self.match.ban1['name']}"
			else:
				placeholder = f"Select {self.match.player1.display_name}\'s Ban"
		elif 'player2' in custom_id:
			if self.match.ban2:
				placeholder = f"{self.match.player2.display_name} bans {self.match.ban2['name']}"
			else:
				placeholder = f"Select {self.match.player2.display_name}\'s Ban"

		songOpts = []
		#Only allow saves for player1 for now, needs to move to "higher seed"
		if self.match.savesEnabled and 'player1' in custom_id:
			songOpts.append(discord.SelectOption(label="Song Save", description="No ban used"))
			maxVals = 2
		else:
			maxVals = 1

		for song in self.match.setlist:
			if (self.match.ban1 and song['name'] in self.match.ban1['name']) or (self.match.ban2 and song['name'] in self.match.ban2['name']):
				continue
			else:
				theSong = discord.SelectOption(label=song['name'], description=f"{song['artist']} - {song['charter']}")
				songOpts.append(theSong)

		super().__init__(placeholder=placeholder, max_values=maxVals, options=songOpts, custom_id=custom_id)

	async def callback(self, interaction: discord.Interaction):
		index = 0
		theSong = {}

		if len(self.values) == 1 and "Song Save" in self.values[0]:
			await interaction.respond("When selecting a save, please also select a song", ephemeral=True, delete_after=5)
			return
		elif self.match.savesEnabled and "Song Save" in self.values[0]:
			self.usedSave = True
			index = 1
		elif self.match.savesEnabled and len(self.values) > 1 and  not "Song Save" in self.values[0]:
			await interaction.respond("When using song saves, only select Song Save alongside another song", ephemeral=True, delete_after=5)
			return

		for song in self.match.setlist:
			if self.values[index] in song['name']:
				theSong = song
				#Might be better to place this elsewhere? This seems to be best for now
				theSong['save'] = True if self.usedSave else False
				break

		if "player1" in self.custom_id:
			self.match.ban1 = theSong
		elif "player2" in self.custom_id:
			self.match.ban2 = theSong

		await self.match.showTool(interaction)

class SongRoundSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		if self.match.roundSngPlchldr != "":
			placeholder = f"Song Played: {self.match.roundSngPlchldr}"
		else:
			placeholder = "Song Played"

		playedSongs = []
		for rnd in self.match.rounds:
			playedSongs.append(rnd['song'])

		songOpts = []
		for song in self.match.setlist:
			if (song['name'] in self.match.ban1['name'] and not self.match.ban1['save']):
				continue
			elif song['name'] in self.match.ban2['name'] or song['name'] in playedSongs:
				continue
			else:
				theSong = discord.SelectOption(label=song['name'], description=f"{song['artist']} - {song['charter']}")
				songOpts.append(theSong)
		super().__init__(placeholder=placeholder, max_values=1, options=songOpts, custom_id="roundsong_sel")

	async def callback(self, interaction: discord.Integration):
		self.match.roundSngPlchldr = self.values[0]
		await self.match.showTool(interaction)

class PlayerRoundSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		if self.match.roundWinPlchldr:
			placeholder = f"Round Winner: {self.match.roundWinPlchldr.display_name}"
		else:
			placeholder = "Round Winner"

		player1 = discord.SelectOption(label=self.match.player1.display_name)
		player2 = discord.SelectOption(label=self.match.player2.display_name)
		super().__init__(placeholder=placeholder, max_values=1, options=[player1, player2], custom_id="roundwin_sel")

	async def callback(self, interaction: discord.Integration):
		if self.values[0] == self.match.player1.display_name:
			winner = self.match.player1
		elif self.values[0] == self.match.player2.display_name:
			winner = self.match.player2

		self.match.roundWinPlchldr = winner
		await self.match.showTool(interaction)

class BracketSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match

	async def init(self):
		brackets = []
		for bracket in await self.get_brackets():
			brackets.append(discord.SelectOption(label=bracket.name))
		super().__init__(max_values=1, options=brackets, custom_id="bracket_sel")

	@sync_to_async
	def get_brackets(self):
		return list(self.match.tourney.brackets.all())

	@sync_to_async
	def set_bracket(self, bracket):
		self.match.bracket = self.match.tourney.brackets.get(name=bracket, tournament=self.match.tourney)

	async def callback(self, interaction: discord.Integration):
		await self.set_bracket(self.values[0])
		await self.match.showTool(interaction)

class GroupSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match

	async def init(self):
		groups = []
		for group in await self.get_groups():
			groups.append(discord.SelectOption(label=group.name))
		super().__init__(max_values=1, options=groups, custom_id="group_sel")

	@sync_to_async
	def get_groups(self):
		return list(self.match.bracket.groups.all())

	@sync_to_async
	def set_bracket_group(self, group):
		self.match.group = self.match.bracket.groups.get(name=group, bracket=self.match.bracket)

	async def callback(self, interaction: discord.Integration):
		await self.set_bracket_group(self.values[0])
		await self.match.showTool(interaction)

class PlayerSelect(discord.ui.Select):
	def __init__(self, match, custom_id):
		self.match = match
		self.cid = custom_id #Discord doesn't let us access underlying attributes until super() is called

	async def init(self):
		dis = True
		if 'player1' in self.cid:
			if self.match.bracket.num_players == 2:
				placeholder = "High Seed"
			else:
				placeholder = "Player 1"

			if len(self.match.players) > 0:
				placeholder += f" - {self.match.players[0].ch_name}"
			if len(self.match.players) == 0:
				dis = False

		elif 'player2' in self.cid:
			if self.match.bracket.num_players == 2:
				placeholder = "Low Seed"
			else:
				placeholder = "Player 2"

			if len(self.match.players) > 1:
				placeholder += f" - {self.match.players[1].ch_name}"
			if len(self.match.players) == 1:
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

		players = []
		for player in await self.get_players():
			players.append(discord.SelectOption(label=player.ch_name))
		super().__init__(placeholder=placeholder, max_values=1,	options=players, custom_id=self.cid)
		if dis:
			self.disabled = True

	@sync_to_async
	def get_players(self) -> list:
		id_list = []
		for player in self.match.players:
			id_list.append(player.id)
		return list(self.match.group.players.all().exclude(id__in=id_list))

	@sync_to_async
	def set_player(self, ch_name: str):
		self.match.players.append(self.match.group.players.get(ch_name=ch_name))

	async def callback(self, interaction: discord.Interaction):
		await self.set_player(self.values[0])
		await self.match.showTool(interaction)

#This class is being written with the assumption of official tournament matches - exhibition can be made to extend this with custom logging/rules
class DiscordMatch():
	def __init__(self, message):
		self.msg = message
		self.ref = message.user if hasattr(message, 'user') else None
		self.channel = message.channel if hasattr(message, 'channel') else None
		self.tourney = None
		self.bracket = None
		self.group = None
		self.setlist = None
		self.players = []
		self.bans = []
		self.rounds = []
		
		#Corp tourney saves framework
		self.savesEnabled = True
		self.confirmCancel = False
		#TODO - figure out how to allow exhibition matches(?)

	async def init(self) -> bool:
		self.tourney = await self.get_tournament_from_guild(self.msg.guild)#Assuming single tourney for now
		if not self.tourney:
			await message.respond("No active tourney - running exhibition mode not supported now", ephemeral=True)
			return False

	async def finishMatch(self, interaction):
		#Save match results to DB
		await interaction.edit(embeds=[self.genMatchEmbed()], content=None, view=None)

	async def showTool(self, interaction):
		view = DiscordMatchView(self)
		await view.init()
		self.msg = await interaction.edit(embeds=[self.genMatchEmbed()], content=None, view=view)

	@sync_to_async
	def get_tournament_from_guild(self, guild: discord.Guild) -> Tournament:
		return Tournament.objects.get(guild=guild.id, active=True)

	def genMatchEmbed(self):
		embed = discord.Embed(colour=0x3FFF33)
		embed.set_author(name=f"Ref: {self.ref.display_name}", icon_url=self.ref.avatar.url)

		if not self.bracket:
			embed.add_field(name="Bracket", value=f"{self.tourney.short_name}\nSelect which bracket the match is for", inline=False)
			return embed

		if not self.group:
			embed.add_field(name="Group", value=f"{self.tourney.short_name} - {self.bracket.name}\nSelect which group the match is for", inline=False)
			return embed

		if len(self.players) < self.bracket.num_players:
			embed.add_field(name="Group", value=f"{self.tourney.short_name} - {self.bracket.name} - Group {self.group.name}\nSelect which players the match is for", inline=False)
			return embed
			#embed.add_field(name="Players", value=f"{self.player1.mention}({}) vs {self.player2.mention}", inline=False)

		if len(self.bans) > 0:
			if self.savesEnabled and self.ban1['save']:
				embed.add_field(name="Bans", value=f"{self.player1.mention} saves {self.ban1['name']}\n{self.player2.mention} bans {self.ban2['name']}", inline=False)
			else:
				embed.add_field(name="Bans", value=f"{self.player1.mention} bans {self.ban1['name']}\n{self.player2.mention} bans {self.ban2['name']}", inline=False)
		elif self.playersPicked and not self.bansPicked:
			embed.add_field(name="Bans", value="Select bans then hit submit to continue", inline=False)

		if self.playersPicked and self.bansPicked:
			if len(self.rounds) > 0:
				rndStr = ""
				ply1Wins = 0
				ply2Wins = 0
				for i, rnd in enumerate(self.rounds):
					if i == 0:
						playerPick = self.player1 #Need to figure out this on ban deferrals
					else:
						if self.rounds[i-1]['winner'].id == self.player1.id:
							playerPick = self.player2
						else:
							playerPick = self.player1
						
					if rnd['winner'].id == self.player1.id:
						ply1Wins += 1
					else:
						ply2Wins += 1

					rndStr += f"{playerPick.mention} Picks - {rnd['song']} - {rnd['winner'].mention} wins!\n\n"

				if ply1Wins >= math.ceil(self.numRounds/2):
					rndStr += f"{self.player1.mention} WINS!"
					embed.title = "Match Results" 
				elif ply2Wins >= math.ceil(self.numRounds/2):
					rndStr += f"{self.player2.mention} WINS!"
					embed.title = "Match Results"
				else:
					#TODO - Get bracket name added in the title
					embed.title = "Current Match Results"

				embed.add_field(name="Played Rounds", value=rndStr, inline=False)
			else:
				embed.add_field(name="Played Rounds", value="No rounds played yet", inline=False)

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
		elif len(self.match.players) < self.match.bracket.num_players:
			self.add_item(self.back)
			for i in range(self.match.bracket.num_players):
				sel = PlayerSelect(self.match, f"player{i+1}_sel")
				await sel.init()
				self.add_item(sel)
		elif self.match.playersPicked and not self.match.bansPicked:
			bans = discord.ui.Button(label="Submit Bans", style=discord.ButtonStyle.secondary, custom_id="bansBtn")
			bans.callback = self.bansBtn

			if (not self.match.ban1 or not self.match.ban2) and not self.match.savesEnabled: #This is is not needed once the saves are implemented
				bans.disabled = True

			self.add_item(bans)
			self.add_item(BanSelect(self.match, "player1_ban"))
			self.add_item(BanSelect(self.match, "player2_ban"))
		elif self.match.playersPicked and self.match.bansPicked:
			rounds = discord.ui.Button(label="Add Round", style=discord.ButtonStyle.secondary, custom_id="roundBtn")
			rounds.callback = self.roundBtn

			if self.match.roundWinPlchldr == None or self.match.roundSngPlchldr == "":
				rounds.disabled = True
			
			self.add_item(rounds)

			submit = discord.ui.Button(label="Submit", style=discord.ButtonStyle.green, custom_id="submitBtn")
			submit.callback = self.submitBtn

			ply1Wins = 0
			ply2Wins = 0
			for rnd in self.match.rounds:
				if rnd['winner'].id == self.match.player1.id:
					ply1Wins += 1
				elif rnd['winner'].id == self.match.player2.id:
					ply2Wins += 1

			if ply1Wins < math.ceil(self.match.numRounds/2) and ply2Wins < math.ceil(self.match.numRounds/2):
				submit.disabled = True
				self.add_item(SongRoundSelect(self.match))
				self.add_item(PlayerRoundSelect(self.match))

			self.add_item(submit)

	async def interaction_check(self, interaction: discord.Interaction):
		if interaction.user.id == self.match.ref.id:
			return True
		else:
			await interaction.response.send_message("You are not the ref for this match", ephemeral=True, delete_after=5)
			return False

	async def backBtn(self, interaction: discord.Interaction):
		if self.match.group:
			self.match.group = None
		elif self.match.bracket:
			self.match.bracket = None
		await self.match.showTool(interaction)

	async def cancelBtn(self, interaction: discord.Interaction):
		if self.match.confirmCancel:
			await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
			await self.match.matchDB.cancelMatch(self.match)
			self.stop()
		else:
			self.match.confirmCancel = True
			await interaction.response.send_message(content="Are you sure you want to cancel? Click cancel again to confirm", ephemeral=True, delete_after=5)

	async def playersBtn(self, interaction: discord.Interaction):
		self.match.playersPicked = True
		self.stop()
		await self.match.showTool(interaction)

	async def bansBtn(self, interaction: discord.Interaction):
		self.match.bansPicked = True
		await self.match.showTool(interaction)

	async def roundBtn(self, interaction: discord.Interaction):
		await interaction.response.defer(invisible=True)
		self.match.rounds.append({ 'song' : self.match.roundSngPlchldr, 'winner' : self.match.roundWinPlchldr })
		self.match.roundWinPlchldr = None
		self.match.roundSngPlchldr = ""
		await self.match.showTool(interaction)

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
		message = await ctx.respond("Setting up")
		match = DiscordMatch(message)
		await match.init()
		await match.showTool(message)

	@match.command(name='reftool', description='Match report done with the ref tool', integration_types={discord.IntegrationType.guild_install})
	async def refToolCmd(self, ctx):
		await ctx.respond.send_modal(modal=RefToolModal())

def setup(bot):
	bot.add_cog(TourneyCmds(bot))
