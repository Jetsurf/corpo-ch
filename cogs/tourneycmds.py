from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

class RefToolModal(Modal)
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

class DiscordBansModal(Modal)
	def __init__(self, *args, **kwargs):
		self.title="Ban Selections"
		#self.setlist = setlist - don't need to make this a class variable -b not needed outside of init
		self.players = players
		super().__init__(*args, **kwargs)
		self.bans = {}

		#Pseudocode until MySQL schema is set
		songOpts = []
		for song in setlist:
			theSong = discord.SelectOption(label=song.name, description=f"{song.artist} - {song.charter}")
			songOpts.append(theSong)

		self.add_item(discord.ui.select(placeholder=f"{self.players[0].name} ban selection", max_values=1, options=songOpts))
		self.add_item(discord.ui.select(placeholder=f"{self.players[1].name} ban selection", max_values=1, options=songOpts))

	async def callback(self, interaction: discord.Interaction):
		#need sanity checking first - ensure that the same song wasn't picked twice
		await interaction.response.send_message("Accepting bans blindly!", ephemeral=True)
		self.bans[self.players[0].id] = self.children[0].value
		self.bans[self.players[1].id] = self.children[1].value
		self.stop()

class DiscordRoundModal(Modal)
	def __init__(self, *args, **kwargs):
		self.title="Round Submission"
		super().__init__(*args, **kwargs)
		self.setlist = setlist
		self.bans = bans
		self.result = None
		songOpts = []
		#figure out how the player pick order works in main class and pass into this class
		#pseudocode until schema is in place
		for song in setlist:
			if song.name in bans: #Needs a way to get values from the bans dict
				continue
			else:
				theSong = discord.SelectOption(label=song.name, description=f"{song.artist} - {song.charter}")
				songOpts.append(theSong)

		self.add_item(discord.ui.select(placeholder=f"{self.players['previousLoser']} song pick", max_values=1, options=songOpts))#players won't be a dict, but still need to determin loser of last round
		self.add_item(discord.ui.select(placeholder="Song winner", max_values=1, options=players))#need to likely construct a list from the discord objects(?)

	async def callback(self, interaction: discord.Interaction):
		#need sanity checking first, but placeholder for now
		await interaction.response.send_message("Accepting your round blindly for now!", ephemeral=True)
		self.result = {'songPick' : self.children[0], 'winner' : self.children[1]}
		self.stop()

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
		self.bans = {} #Dict for discord userid -> song ban
		self.numRounds = 7 #Need to get the number of rounds from the tournament settings
		self.setlist = None #ID for setlist inside of tourney that contains songs - can we tee off of a channel id in discord?
		##NOTE - we may be able to have a command to set a channel in discord for specifc 
		self.players = [] #List for discord user objects - can we feed players into this object from the above (specifically for group stages)
		self.tourney = None #ID for tourney in MySQL - based on discord server id obtained from ctx.guild.id
		self.confirmCancel = False
		self.playersPicked = False
		self.bansDone = False
		self.shown = False
		#TODO - figure out handling on groups stage vs playoffs

	async def cancelMatch(self):
		pass #to implement

	async def showTool(self):
		pass #not ready to let this execute
		embed = await self.genMatchEmbed()
		if self.shown:
			await self.ctx.interaction.edit_original_response(embeds=[embed], view=DiscordMatchView, ephemeral=True)
		else:
			await self.ctx.respond(embeds=[embed], view=DiscordMatchView, ephemeral=True)

	async def previewMatchResult(self):
		#On Submit, show preview of embed with ephemeral=True to confirm all data?
		pass

	async def genMatchEmbed(self):
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "Current Match Results"
		#add players
		#add bans
		#add completed rounds

		return embed

	async def genResultEmbed(self):
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = f"BRACKET/SETLISTNAME Match Results"
		embed.set_author(name=f"Ref: {self.ctx.user.display_name}", icon_url=self.ctx.user.avatar.url)

		return embed

class DiscordMatchView():
	def __init__(self, match):
		super().__init__()
		self.match = match
		self.timeout = None #Timeout of 0 makes view persistent - ALL discord objects need a custom_id defined as well

		#not using decorators as buttons will be placed dynamically
		cancel = discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancelBtn")
		cancel.callback = self.cancelBtn
		self.add_item(cancel)

		players = discord.ui.button(label="Player Select", style=discord.ButtonStyle.secondary, custom_id="playersBtn")
		players.callback = self.bansBtn
		bans = discord.ui.button(label="Bans", style=discord.ButtonStyle.secondary, custom_id="bansBtn")
		bans.callback = self.bansBtn
		rounds = discord.ui.button(label="Add Round", style=discord.ButtonStyle.secondary, custom_id="roundBtn")
		rounds.callback = self.roundBtn
		submit = discord.button(label+"Submit", style.ButtonStyle.green, custom_id="submitBtn")
		submit.callback = self.submitBtn

		#Logic for doing self.add_item on buttons to populate them in view
			
		#Perform check if one user has amount of wins necessary to complete a match, then enable submit button
			
	async def cancelBtn(self, interaction: discord.Interaction):
		if self.match.confirmCancel:
			await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
			await self.cancelMatch()
			self.stop()
		else:
			self.match.confirmCancel = True
			await interaction.response.send_message(content="Are you sure you want to cancel? Click cancel again to confirm", ephemeral=True, delete_after=10)

	async def playersBtn(self, interaction: discord.Interaction):
		await interaction.response.send_message("Not implemented yet")

	async def bansBtn(self, interaction: discord.Interaction):
		await interaction.response.send_message("Not implemented yet")

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
		await path.show()

	@match.command(name='reftool', description='Match report done with the ref tool', integration_types={discord.IntegrationType.guild_install})
	async def refToolCmd(self, ctx):
		await ctx.respond.send_modal(modal=RefToolModal())

def setup(bot):
	bot.add_cog(TourneyCmds(bot))
