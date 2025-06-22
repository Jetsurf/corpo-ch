import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

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

class PlayerSelect(discord.ui.Select):
	def __init__(self, match, custom_id):
		self.match = match
		if 'player1' in custom_id:
			placeholder = "Player 1"
		elif 'player2' in custom_id:
			placeholder = "Player 2"

		super().__init__(placeholder=placeholder, max_values=1,	select_type=discord.ComponentType.user_select, custom_id=custom_id)

	async def callback(self, interaction: discord.Interaction):
		if "player1" in self.custom_id:
			self.match.player1 = self.values[0]
			await interaction.respond(f"Player 1 is {self.values[0].display_name}", ephemeral=True, delete_after=5)
		elif "player2" in self.custom_id:
			self.match.player2 = self.values[0]
			await interaction.respond(f"Player 2 is {self.values[0].display_name}", ephemeral=True, delete_after=5)

		await self.match.showTool()

class SongRoundSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		songOpts = []
		for song in self.match.setlist:
			if song in self.match.ban1 or song in self.match.ban2:
				continue
			else:
				theSong = discord.SelectOption(label=song['name'], description=f"{song['artist']} - {song['charter']}")
				songOpts.append(theSong)
		super().__init__(placeholder="Song Played", max_values=1, options=songOpts, custom_id="roundsong_sel")

	async def callback(self, interaction: discord.Integration):
		pass

class PlayerRoundSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		super().__init__(placeholder="Winning Player", max_values=1, select_type=discord.ComponentType.user_select, options=[self.match.player1, self.match.player2], custom_id="roundwin_sel")

	async def callback(self, interaction: discord.Integration):
		pass

class BanSelect(discord.ui.Select):
	def __init__(self, match, custom_id):
		self.match = match

		if 'player1' in custom_id:
			if self.match.ban1:
				placeholder = f"{self.match.player1.display_name} bans {self.match.ban1['name']}"
			else:
				placeholder = f"Select {self.match.player1.display_name}\'s Ban"
		elif 'player2' in custom_id:
			if self.match.ban2:
				placeholder = f"{self.match.player2.display_name} bans {self.match.ban2['name']}"
			else:
				placeholder = f"Select {self.match.player2.display_name}\'s Ban"

		songOpts = []
		for song in self.match.setlist:
			theSong = discord.SelectOption(label=song['name'], description=f"{song['artist']} - {song['charter']}")
			songOpts.append(theSong)

		super().__init__(placeholder=placeholder, max_values=1,	options=songOpts, custom_id=custom_id)

	async def callback(self, interaction: discord.Interaction):
		theSong = {}
		for song in self.match.setlist:
			if self.values[0] in song['name']:
				theSong = song
				break

		if "player1" in self.custom_id:
			self.match.ban1 = theSong
			await interaction.respond(f"Player 1 is {self.values[0]}", ephemeral=True, delete_after=5)
		elif "player2" in self.custom_id:
			self.match.ban2 = theSong
			await interaction.respond(f"Player 2 is {self.values[0]}", ephemeral=True, delete_after=5)

		await self.match.showTool()

##Need modal for groups/player selection

class DiscordMatchDB():
	def __init__(self):
		#will require storing the current match data generated in DiscordMatch() into the DB until submitted
		#need DB schema in place to reload a persistent view properly
		pass

class DiscordMatch():
	def __init__(self, ctx):
		self.ctx = ctx
		self.rounds = [] #list to append a dict of a match result
		self.numRounds = 7 #Need to get the number of rounds from the tournament settings
		self.setlist = [ #Test Data
		{"name" : "Conjunction", "artist" : "Casiopea", "charter" : "JoeyD" },
		{"name" : "Cutting Edge", "artist" : "Kiko Loureiro", "charter" : "Thundahk" },
		{"name" : "Break Your Crank", "artist" : "Guilhem Desq", "charter" : "Aren Eternal" },
		{"name" : "Prayer Position", "artist" : "Endarkenment", "charter" : "Chezy" },
		{"name" : "Endarkenment", "artist" : "Anaal Nathrakh", "charter" : "Miscellany" },
		{"name" : "Chakh Le", "artist" : "Bloodywood", "charter" : "Figneutered" },
		{"name" : "Que Pasa (feat. Dave Mustaine)", "artist" : "John 5", "charter" : "OHM" },
		{"name" : "You Think I Ain't Worth a Dollar", "artist" : "Erra", "charter" : "NCV" },
		{"name" : "Crownless", "artist" : "Nightwish", "charter" : "Jackie & Aren Eternal" },
		{"name" : "Orange Grove", "artist" : "Unprocessed", "charter" : "Deltarak" },
		]
		#self.setlist = None #ID for setlist inside of tourney that contains songs - can we tee off of a channel id in discord?
		##NOTE - we may be able to have a command to set a channel in discord for specifc brackets(?)
		self.player1 = None
		self.player2 = None
		self.ban1 = None
		self.ban2 = None
		#self.tourney = None #ID for tourney in MySQL - based on discord server id obtained from ctx.guild.id
		self.confirmCancel = False
		self.playersPicked = False
		self.bansPicked = False
		self.shown = False
		#TODO - figure out handling on groups stage vs playoffs

	async def init(self):
		pass

	async def cancelMatch(self):
		pass #to implement

	async def showTool(self):
		pass #not ready to let this execute
		embed = await self.genMatchEmbed()
		if self.shown:
			await self.ctx.interaction.edit_original_response(embeds=[embed], view=DiscordMatchView(self))
		else:
			await self.ctx.respond(embeds=[embed], view=DiscordMatchView(self), ephemeral=True)
			self.shown = True

	async def previewMatchResult(self):
		#On Submit, show preview of embed with ephemeral=True to confirm all data?
		pass

	async def genMatchEmbed(self):
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "Current Match Results"
		if self.playersPicked:
			embed.add_field(name="Players", value=f"{self.player1.display_name} vs {self.player2.display_name}", inline=False)
		else:
			embed.add_field(name="Players", value=f"Select players then hit submit to start", inline=False)

		if self.bansPicked:
			embed.add_field(name="Bans", value=f"{self.player1.display_name} bans {self.ban1['name']}\n{self.player2.display_name} bans {self.ban2['name']}", inline=False)
		else:
			embed.add_field(name="Bans", value="Select bans then hit submit to continue", inline=False)

		#add completed rounds

		return embed

	async def genResultEmbed(self):
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = f"BRACKET/SETLISTNAME Match Results"
		embed.set_author(name=f"Ref: {self.ctx.user.display_name}", icon_url=self.ctx.user.avatar.url)

		return embed

class DiscordMatchView(discord.ui.View):
	def __init__(self, match):
		super().__init__()
		self.match = match
		self.timeout = None #Timeout of 0 makes view persistent - ALL discord objects need a custom_id defined as well

		#not using decorators as buttons will be placed dynamically
		cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancelBtn")
		cancel.callback = self.cancelBtn
		self.add_item(cancel)

		if not self.match.playersPicked:
			players = discord.ui.Button(label="Players Submit", style=discord.ButtonStyle.secondary, custom_id="playersBtn")
			players.callback = self.playersBtn

			if not self.match.player1 or not self.match.player2:
				players.disabled = True

			self.add_item(players)
			self.add_item(PlayerSelect(self.match, "player1_sel"))
			self.add_item(PlayerSelect(self.match, "player2_sel"))
		elif self.match.playersPicked and not self.match.bansPicked:
			bans = discord.ui.Button(label="Submit Bans", style=discord.ButtonStyle.secondary, custom_id="bansBtn")
			bans.callback = self.bansBtn

			if not self.match.ban1 or not self.match.ban2:
				bans.disabled = True

			self.add_item(bans)
			self.add_item(BanSelect(self.match, "player1_ban"))
			self.add_item(BanSelect(self.match, "player2_ban"))

		rounds = discord.ui.Button(label="Add Round", style=discord.ButtonStyle.secondary, custom_id="roundBtn")
		rounds.callback = self.roundBtn
		submit = discord.ui.Button(label="Submit", style=discord.ButtonStyle.green, custom_id="submitBtn")
		submit.callback = self.submitBtn

		
		
		#self.add_item(rounds)
			
		#Perform check if one user has amount of wins necessary to complete a match, then enable submit button
			
	async def cancelBtn(self, interaction: discord.Interaction):
		if self.match.confirmCancel:
			await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
			await self.cancelMatch()
			self.stop()
		else:
			self.match.confirmCancel = True
			await interaction.response.send_message(content="Are you sure you want to cancel? Click cancel again to confirm", ephemeral=True, delete_after=5)

	async def playersBtn(self, interaction: discord.Interaction):
		self.match.playersPicked = True
		await interaction.response.send_message(f"Selected players {self.match.player1.display_name} and {self.match.player2.display_name} for match", ephemeral=True, delete_after=5)
		self.stop()
		await self.match.showTool()

	async def bansBtn(self, interaction: discord.Interaction):
		self.match.bansPicked = True
		await interaction.response.send_message("Bans selected!", ephemeral=True, delete_after=5)
		await self.match.showTool()

	async def roundBtn(self, interaction: discord.Interaction):
		await interaction.response.send_message("Not implemented yet")

	async def submitBtn(self, interaction: discord.Interaction):
		await interaction.response.send_message("Not implemented yet")

class TourneyCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	tourney = discord.SlashCommandGroup('tourney','Clone Hero Tournament Commands')
	match = tourney.create_subgroup('match', 'Tourney Match Reporting Commands')

	@match.command(name='discord',description='Match reporting done within discord', integration_types={discord.IntegrationType.guild_install})
	async def discordMatchCmd(self, ctx):
		#TODO - Self Ref Match Check setup (DM user that didn't run the command to confirm?)
		#     - Can bypass above with having a "Ref" role assigned
		path = DiscordMatch(ctx)
		await path.init()
		await path.showTool()

	@match.command(name='reftool', description='Match report done with the ref tool', integration_types={discord.IntegrationType.guild_install})
	async def refToolCmd(self, ctx):
		await ctx.respond.send_modal(modal=RefToolModal())

def setup(bot):
	bot.add_cog(TourneyCmds(bot))
