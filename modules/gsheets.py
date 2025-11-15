import re, gspread, tourneysql, asyncio, discord
from datetime import datetime

ssema = asyncio.Semaphore(1) #Semaphore for stats sheet

class GSheets():
	def __init__(self, bot: discord.Bot, sql: tourneysql.TourneyDB, tid: int):
		self.bot = bot
		self.tid = tid
		self.sql = sql
		self.gc = gspread.service_account(filename="config/gsheets-key.json")
		self.frmtBorder = {'textFormat': {'bold': False}, "horizontalAlignment": "CENTER", 'borders': {'right': {'style' : 'SOLID'}, 'left': {'style' : 'SOLID' }}}

	async def init(self, sheet: str) -> bool: #sheet is an arbitrary string "qualifier", "livematch" and "stats"
		self.tourneyConf = await self.sql.getTourneyConfig(self.tid)

		if "disable_gsheets" in self.tourneyConf and self.tourneyConf['disable_gsheets']:
			return True

		#Create Sheet
		if "qualifier_sheet" not in self.tourneyConf and "qualifier" in sheet:
			try:
				self.qualiSheet = self.gc.open(f"{self.tourneyConf['name']} - Qualifier Submissions")
			except:
				return False

			print(f"Setting up quali sheet for {self.tourneyConf['name']} : {self.qualiSheet.url}")
			self.ws = self.qualiSheet.add_worksheet(title="Raw Qualifier Submissions", rows=2, cols=12)
			self.ws.update_acell("A1", "DO NOT EDIT THIS WORKSHEET UNLESS TOLD TO OTHERWISE")
			self.ws.format("A1", {'textFormat': {'bold': True }})
			self.ws.update([["Discord Name", "Clone Hero Name", "Score", "Notes Missed", "Notes Hit", "Overstrums", "Ghosts", "Phrases Earned", "Submission Timestamp", "Screenshot Timestamp", "Image URL", "Game Version" ]], "A2:L2")
			self.ws.format("A2:L2", {'textFormat': {'bold': True}, "horizontalAlignment": "CENTER", 'borders': { 'bottom': { 'style' : 'SOLID' }, 'left': { 'style' : 'SOLID' }, 'right': { 'style' : 'SOLID' }}})
			self.tourneyConf['qualifier_sheet'] = self.qualiSheet.url
			await self.sql.setTourneyConfig(self.tid, self.tourneyConf)
		elif "qualifier" in sheet:
			self.qualiSheet = self.gc.open_by_url(self.tourneyConf['qualifier_sheet'])
			self.qualiws = self.qualiSheet.worksheet("Raw Qualifier Submissions")

		if 'livematch_sheet' not in self.tourneyConf and "livematch" in sheet:
			try:
				self.liveMatchSheet = self.gc.open(f"{self.tourneyConf['name']} - Live Match Data")
				print(f"Setting up live match sheet for {self.tourneyConf['name']} : {self.liveMatchSheet.url}")
				self.lmws = self.liveMatchSheet.worksheet("match_data")
				self.tourneyConf['livematch_sheet'] = self.liveMatchSheet.url
				await self.sql.setTourneyConfig(self.tid, self.tourneyConf)
			except:
				return False
		elif "livematch" in sheet:
			self.liveMatchSheet = self.gc.open_by_url(self.tourneyConf['livematch_sheet'])
			self.lmws = self.liveMatchSheet.worksheet("match_data")

		if 'stats_sheet' not in self.tourneyConf and "stats" in sheet:
			try:
				self.statsSheet = self.gc.open(f"{self.tourneyConf['name']} - Airtable")
				print(f"Setting up quali sheet for {self.tourneyConf['name']} : {self.statsSheet.url}")
				self.sws = self.statsSheet.worksheet("match_data")
				self.tourneyConf['stats_sheet'] = self.statsSheet.url
				await self.sql.setTourneyConfig(self.tid, self.tourneyConf)
			except:
				return False
		elif "stats" in sheet:
			self.statsSheet = self.gc.open_by_url(self.tourneyConf['stats_sheet'])
			self.sws = self.statsSheet.worksheet("match_data")

		return True

	def fixSongName(self, song: str, setlist: dict) -> str:
		name = song
		songData = setlist['set_list'][song]

		if songData['speed'] != 100:
			name += f" ({songData['speed']}%)"
		if "NoModifiers" not in songData['modifiers']:
			#Gross
			mods = re.sub('[a-z]', '', str(songData['modifiers'])).replace(" ", "").replace("'", "")
			name += f" {mods}"

		return name

	async def submitLiveMatch(self, match) -> bool:
		if "disable_gsheets" in self.tourneyConf and self.tourneyConf['disable_gsheets']:
			return True

		brackets = await self.sql.getTourneyBrackets(match['tourneyid'])
		bracket = brackets[self.tourneyConf['name']]
		matchJson = match['matchjson']
		ply1 = matchJson['highSeed']
		ply2 = matchJson['lowSeed']
		#Dirty hard-coded indexes for now to get this working - this is going to need to be changed
		ply1Pts = ply1['points'] if 'points' in ply1 else 0
		ply2Pts = ply2['points'] if 'points' in ply1 else 0
		matchList = [match['matchuuid'], ply1['name'], ply1Pts, ply1['ban'][0], ply1['ban'][1], ply2['name'], ply2Pts, ply2['ban'][0], ply2['ban'][1], matchJson['setlist'], matchJson['winner'] ]
		for song in matchJson['rounds']:
			matchList.append(song['pick'])
			matchList.append(self.fixSongName(song['song'], bracket))

		if 'tb' in matchJson:
			matchList.append(self.fixSongName(matchJson['tb']['song'], bracket))
		else:
			matchList.append("")

		for song in matchJson['rounds']:
			matchList.append(song['winner'])

		if 'tb' in matchJson:
			matchList.append(matchJson['tb']['winner'])
		else:
			matchList.append("")

		if match['sheetrow'] is None:
			print("Adding new row to sheet...")
			self.lmws.append_row(matchList)
			numRows = len(self.lmws.get_all_values())
		
			self.lmws.format(f"A{numRows}:AE{numRows}", self.frmtBorder)
			match['sheetrow'] = numRows
			await self.sql.replaceRefToolMatch(match['matchuuid'], match['tourneyid'], match['finished'], matchJson, match['sheetrow'], match['postid'])
		else:
			self.lmws.update([matchList], f"A{match['sheetrow']}:AE{match['sheetrow']}")

	async def submitMatchResults(self, match, tourney) -> bool:
		if "disable_gsheets" in self.tourneyConf and self.tourneyConf['disable_gsheets']:
			return True

		print(f"Submitting {match['matchuuid']} to airtable")
		brackets = await self.sql.getTourneyBrackets(match['tourneyid'])
		bracket = brackets[self.tourneyConf['name']]
		matchJson = match['matchjson']
		ply1 = matchJson['highSeed']
		ply2 = matchJson['lowSeed']
		matchName = f"{ply1['name']} vs {ply2['name']}"

		for song in matchJson['rounds']:
			ply1List = []
			ply2List = []
			ply1Fnd = {}
			ply2Fnd = {}

			if song['index'] == 1:
				ply1List.append(matchName)
				ply2List.append("")
			else:
				ply1List.append("")
				ply2List.append("")

			ply1List.append(self.fixSongName(song['song'], bracket))
			ply2List.append(self.fixSongName(song['song'], bracket))

			stegData = song['steg_data']
			for ply in stegData['players']:
				if ply1['name'] == ply['profile_name']:
						ply1Fnd = ply
						continue
				if ply2['name'] == ply['profile_name']:
						ply2Fnd = ply
						continue

			ply1List.append(ply1Fnd['profile_name'])
			ply2List.append(ply2Fnd['profile_name'])
			ply1List.append(ply1Fnd['score'])
			ply2List.append(ply2Fnd['score'])
			ply1List.append(ply1Fnd['notes_missed'])
			ply2List.append(ply2Fnd['notes_missed'])
			ply1List.append(ply1Fnd['overstrums'])
			ply2List.append(ply2Fnd['overstrums'])
			ply1List.append(ply1Fnd['notes_hit'])
			ply2List.append(ply2Fnd['notes_hit'])
			ply1List.append(ply1Fnd['frets_ghosted'])
			ply2List.append(ply2Fnd['frets_ghosted'])
			ply1List.append(f"{datetime.strptime(stegData['score_timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime("%Y-%m-%d %H:%M:%S")}-UTC")
			ply2List.append("")
			ply1List.append(stegData['image_url'])
			ply2List.append("")
			try:
				self.sws.append_row(ply1List)
				numRows = len(self.sws.get_all_values())
				self.sws.format(f"A{numRows}:L{numRows}", self.frmtBorder)
				self.sws.append_row(ply2List)
				numRows = len(self.sws.get_all_values())
				self.sws.format(f"A{numRows}:L{numRows}", self.frmtBorder)
			except Exception as e:
				print(f"Exception in gspread: {e}")
				return False

	async def submitQualifier(self, user, qualifierData: dict) -> bool:
		if "disable_gsheets" in self.tourneyConf and self.tourneyConf['disable_gsheets']:
			return True

		chName = qualifierData['players'][0]['profile_name']
		score = qualifierData['players'][0]['score']
		missed = qualifierData['players'][0]['notes_missed']
		hit = qualifierData['players'][0]['notes_hit']
		os = qualifierData['players'][0]['overstrums']
		ghosts = qualifierData['players'][0]['frets_ghosted']
		phrases = qualifierData['players'][0]['sp_phrases_earned']
		submissionTimestamp = f"{datetime.strptime(qualifierData['submission_timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime("%Y-%m-%d %H:%M:%S")}-UTC"
		screenshotTimestamp = f"{datetime.strptime(qualifierData['score_timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime("%Y-%m-%d %H:%M:%S")}-UTC"
		imgUrl = qualifierData['image_url']
		gameVer = qualifierData['game_version']

		try:
			self.qualiws.append_row([user.global_name, chName, score, missed, hit, os, ghosts, phrases, submissionTimestamp, screenshotTimestamp, imgUrl, gameVer])
			numRows = len(self.ws.get_all_values())
			self.qualiws.format(f"A{numRows}:L{numRows}", self.frmtBorder)
		except Exception as e:
			print(f"Exception in gspread: {e}")
			return False

		return True
