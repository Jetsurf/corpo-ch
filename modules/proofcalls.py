import discord, asyncio, os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import apscheduler.triggers.cron
from collections import Counter

import gsheets
import chutils

class ProofCallModal(discord.ui.DesignerModal):
	def __init__(self, *args, **kwargs):
		self.screens = None
		file = discord.ui.Label("Screenshots to upload for this match", discord.ui.FileUpload(max_values=10, required=True))
		super().__init__(discord.ui.TextDisplay("Screenshot Submission"), file, *args, **kwargs)

	async def callback(self, interaction: discord.Interaction):
		self.screens = self.children[1].item.values
		await interaction.respond("Processing, wait for embed to update", ephemeral=True, delete_after=5)

#class OverStrumFix(discord.ui.View):
#	def __init__(self, match):

class ProofCallView(discord.ui.View):
	def __init__(self, proofcall, msg, tourney, match, *args, **kwargs):
		super().__init__(timeout=None)
		self.msg = msg #if msg != None else self.message
		self.proofCall = proofcall
		self.tourney = tourney
		self.match = match

		## This is for potential discord.ui.DesignerView output to be *fancy* - not now
		#if screens != None:
		#	gallery = discord.ui.MediaGallery()
		#	for screen in screens:
		#		gallery.add_item(screen)
		#	self.add_item(gallery)

		submit = discord.ui.Button(label="Submit Screenshot", style=discord.ButtonStyle.green, custom_id="submitBtn")
		submit.callback = self.submitBtn
		self.add_item(discord.ui.ActionRow(submit))

	async def submitBtn(self, interaction: discord.Interaction):
		modal = ProofCallModal(title="Screenshot Submission")
		await interaction.response.send_modal(modal=modal)
		await modal.wait()
		await self.proofCall.addScreenshots(self.msg, self.tourney, self.match, modal.screens)

	async def interaction_check(self, interaction: discord.Interaction):
		ply1 = await self.proofCall.sql.getPlayerByCHName(self.match['matchjson']['highSeed']['name'], self.tourney['id'])
		ply2 = await self.proofCall.sql.getPlayerByCHName(self.match['matchjson']['lowSeed']['name'], self.tourney['id'])
		ply1 = await self.proofCall.bot.fetch_user(ply1['discordid'])
		ply2 = await self.proofCall.bot.fetch_user(ply2['discordid'])
		refRole = interaction.guild.get_role(self.tourney['config']['ref_role'])
		if ply1.id == interaction.user.id or ply2.id == interaction.user.id or refRole in interaction.user.roles:
			return True
		else:
			await interaction.response.send_message("You are not a player or ref for this match", ephemeral=True, delete_after=5)
			return False

class ProofCalls():
	def __init__(self, bot, *args, **kwargs):
		self.bot = bot
		self.sql = bot.tourneyDB
		self.chUtils = chutils.CHUtils()
		self.scheduler = AsyncIOScheduler()
		self.scheduler.add_job(self.watchRefToolMatches, apscheduler.triggers.cron.CronTrigger(hour="*", minute='*', second='*/10', timezone='UTC'))
		self.scheduler.start()

	async def init(self):
		proofs = await self.sql.getActiveRefToolMatches()
		for match in proofs:
			tourney = await self.sql.getTourney(match['tourneyid'])
			if match['finished'] and match['postid'] != None:
				channel = self.bot.get_channel(tourney['config']['proof_channel'])
				thread = channel.get_thread(match['postid'])
				msg = await thread.fetch_message(match['postid'])

				ply1Db = await self.sql.getPlayerByCHName(match['matchjson']['highSeed']['name'], tourney['id'])
				ply2Db = await self.sql.getPlayerByCHName(match['matchjson']['lowSeed']['name'], tourney['id'])
				ply1 = await self.bot.fetch_user(ply1Db['discordid'])
				ply2 = await self.bot.fetch_user(ply2Db['discordid'])
				print(f"Restarting proof call {match['matchuuid']} with thread id {msg.id}")
				await msg.edit(content=f"Paging {ply1.mention} and {ply2.mention} for screenshots!", embed=self.makeProofEmbed(tourney, match, ply1Db, ply2Db), view=ProofCallView(self, msg, tourney, match))

	async def watchRefToolMatches(self):
		matches = await self.sql.getActiveRefToolMatches()

		for match in matches:
			tourney = await self.sql.getTourney(match['tourneyid'])
			if match['finished'] and match['postid'] == None:
				forumChannel = self.bot.get_channel(tourney['config']['proof_channel'])
				newThr = await self.postProofCall(tourney, forumChannel, match)
				await self.sql.replaceRefToolMatch(match['matchuuid'], tourney['id'], True, match['matchjson'], None, newThr.id)
				sheet = gsheets.GSheets(self.bot, self.sql, tourney['id'])
				await sheet.init("livematch")
				await sheet.submitLiveMatch(match)
			elif 'highSeed' in match['matchjson'] and not match['finished']:
				sheet = gsheets.GSheets(self.bot, self.sql, tourney['id'])
				await sheet.init("livematch")
				await sheet.submitLiveMatch(match)

	async def postProofCall(self, tourney: dict, channel: discord.ForumChannel, match: dict):
		matchJson = match['matchjson']
		print(f"Posting proof call for {tourney['config']['name']} match {matchJson['highSeed']['name']} - {matchJson['lowSeed']['name']}")
		ply1Db = await self.sql.getPlayerByCHName(matchJson['highSeed']['name'], tourney['id'])
		ply2Db = await self.sql.getPlayerByCHName(matchJson['lowSeed']['name'], tourney['id'])

		if ply1Db != None:
			ply1 = await self.bot.fetch_user(ply1Db['discordid'])
		else:
			print(f"Error finding {tourney['name']} player {matchJson['highSeed']['name']}!")

		if ply2Db != None:
			ply2 = await self.bot.fetch_user(ply2Db['discordid'])
		else:
			print(f"Error finding {tourney['name']} player {matchJson['lowSeed']['name']}!")

		#Sanely get the message to pass in, silly threads
		thread = await channel.create_thread(name=f"Proof call: {ply1.name} vs {ply2.name}!", content=f"Setting up! - Paging {ply1.mention} and {ply2.mention} for screenshots!")
		msg = await thread.fetch_message(thread.id)
		await msg.edit(content=f"Paging {ply1.mention} and {ply2.mention} for screenshots!", embed=self.makeProofEmbed(tourney, match, ply1Db, ply2Db), view=ProofCallView(self, msg, tourney, match))

		return thread

	async def addScreenshots(self, msg: discord.Message, tourney: dict, match: dict, screens: list) -> bool: #Bool if match is complete
		print(f"Adding screenshots for match {match['matchuuid']}")
		matchJson = match['matchjson']
		ply1Db = await self.sql.getPlayerByCHName(matchJson['highSeed']['name'], tourney['id'])
		ply2Db = await self.sql.getPlayerByCHName(matchJson['lowSeed']['name'], tourney['id'])
		channel = self.bot.get_channel(tourney['config']['proof_channel'])
		thread = channel.get_thread(msg.id)

		for screen in screens:
			stegData = await self.chUtils.getStegInfo(screen)
			if stegData == None:
				print(f"Invalid steg data {screen.filename}")
				continue

			chartInfo = tourney['brackets'][matchJson['setlist']]['set_list'].get(stegData['song_name'])
			if chartInfo == None:
				print(f"Screenshot {stegData['image_name']} not from setlist")
				continue
			elif chartInfo['checksum'] == stegData['checksum']:
				plysMatched = 0
				for ply in stegData['players']:
					if ply1Db['chname'] == ply['profile_name']:
						plysMatched += 1
					if ply2Db['chname'] == ply['profile_name']:
						plysMatched += 1

				if plysMatched != len(stegData['players']):
					print("Player names for this match are not correct")
					continue

				stegData['image_url'] = f"https://matches.corpo-ch.org/{tourney['config']['name'].replace(" ", "")}/{match['matchuuid']}/{stegData['image_name']}"
			else:
				print(f"Screenshot {stegData['image_name']} not using correct chart")
				continue

			outDir = f"steg/matches/{tourney['config']['name']}/{match['matchuuid']}".replace(" ", "")
			if not os.path.isdir(outDir):
				os.makedirs(outDir)

			if 'tb' in matchJson and matchJson['tb']['song'] == stegData['song_name'] and 'steg_data' not in matchJson['tb']:
				print(f"Adding TB {stegData['song_name']}")
				await screen.save(f"{outDir}/{stegData['image_name']}", seek_begin=True)
				matchJson['tb']['steg_data'] = stegData
			else:
				for song in matchJson['rounds']:
					if song['song'] == stegData['song_name'] and 'steg_data' not in song:
						print(f"Adding {stegData['song_name']}")
						await screen.save(f"{outDir}/{stegData['image_name']}", seek_begin=True)
						embed = self.chUtils.buildStatsEmbed(f"Stats for {stegData['song_name']}", stegData)
						embed.set_image(url=screen.url)
						await thread.send(embed=embed)
						song['steg_data'] = stegData
						break

		successes = sum([1 for d in matchJson['rounds'] if 'steg_data' in d]) + (1 if 'tb' in matchJson else 0)
		needed = len(matchJson['rounds']) + (1 if "tb" in matchJson else 0)
		if needed == successes:
			print(f"Match {match['matchuuid']} complete!")
			await self.sql.saveCompleteMatch(match['matchuuid'], match['tourneyid'], ply1Db['discordid'], ply2Db['discordid'], matchJson)
			await msg.edit(content=f"Match Complete!", embed=self.makeProofEmbed(tourney, match, ply1Db, ply2Db), view=None)
			await thread.archive(locked=True)
			sheet = gsheets.GSheets(self.bot, self.sql, tourney['id'])
			await sheet.init("stats")
			await sheet.submitMatchResults(match, tourney)			
		else:
			await self.sql.replaceRefToolMatch(match['matchuuid'], match['tourneyid'], True, matchJson, None, msg.id)
			await msg.edit(embed=self.makeProofEmbed(tourney, match, ply1Db, ply2Db), view=ProofCallView(self, msg, tourney, match))

	def makeProofEmbed(self, tourney: dict, match: dict, ply1Db: dict, ply2Db: dict) -> discord.Embed:
		matchJson = match['matchjson']
		embed = discord.Embed(colour=0x3FFF33)
		embed.set_footer(text=f"UUID: {match['matchuuid']}")
		ply1 = matchJson['highSeed']
		ply2 = matchJson['lowSeed']

		embed.title = f"{tourney['config']['name']} - {ply1['name']}:{ply1Db['config']['seed']} vs {ply2['name']}:{ply2Db['config']['seed']}"

		embed.add_field(name=f"Points", value=f"{ply1['points']} - {ply2['points']}", inline=False)
		banStr = ""
		if matchJson['defer']:
			banStr += f"{ply1['name']} defers ban pick.\n\n"

		banStr += f"**{ply1['name']} Bans**\n"
		for ban in ply1['ban']:
			banStr += f"{ban}\n"

		banStr += f"\n**{ply2['name']} Bans**\n"
		for ban in ply2['ban']:
			banStr += f"{ban}\n"

		embed.add_field(name="Bans", value=banStr, inline=False)
		rndStr = ""
		for rnd in matchJson['rounds']:
				rndStr += f"{rnd['pick']} picks {rnd['song']} - {rnd['winner']} wins\n\n"

		if 'tb' in matchJson:
			rndStr += f"TIEBREAKER - {matchJson['tb']['song']} - {matchJson['tb']['winner']} wins!\n\n"

		if matchJson['winner'] == 0:
			rndStr += f"{ply1['name']} wins the match!"
		else:
			rndStr += f"{ply2['name']} wins the match!"

		embed.add_field(name="Round Results", value=rndStr, inline=False)

		missingStr = ""
		successStr = ""
		for song in matchJson['rounds']:
			if 'steg_data' in song:
				successStr += f"{song['song']}\n"
			else:
				missingStr += f"{song['song']}\n"

		if 'tb' in matchJson:
			if 'steg_data' in matchJson['tb']:
				successStr += f"{matchJson['tb']['song']}"
			else:
				missingStr += f"{matchJson['tb']['song']}"

		if successStr != "":
			embed.add_field(name="Received Screens", value=successStr, inline=False)
		if missingStr != "":
			embed.add_field(name="Screenshots Needed", value=missingStr, inline=False)
			embed.add_field(name="Instructions", value="Please click 'Submit Screenshot' button to submit the in-game screenshots for this round", inline=False)

		return embed
