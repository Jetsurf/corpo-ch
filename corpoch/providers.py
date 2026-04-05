import requests_cache, json, io, hashlib, re, gspread, asyncio, discord, os, uuid, platform, subprocess, pytesseract, shutil

from datetime import datetime
from django.db import models
from PIL import Image, ImageEnhance
from pydantic import BaseModel
from random import randbytes
from typing import Optional, Union, Literal

from corpoch import __user_agent__
from corpoch import settings
from corpoch.models import GSheetAPI, Chart, Tournament, Match, Qualifier, QualifierSubmission
from corpoch.types import StegScreenshot, SearchResponse, CH_DIFFICULTIES, CH_INSTRUMENTS
from corpoch.utils.hydra.hydra.hyutil import analyze_chart_bytes_chart, analyze_chart_bytes_mid
from corpoch.utils.snghandler import SNGHandler

class EncoreClient:
	def __init__(self, limit: int=24, exact: bool=True):
		#limit 24 for discord view select options limit
		self._session = requests_cache.CachedSession()
		self._session.headers = {
			'User-Agent' : __user_agent__,
			"Content-Type": "application/json"
		}
		# encore.us API urls
		self._encore={}
		self._encore['gen'] = 'https://api.enchor.us/search'
		self._encore['adv'] = 'https://api.enchor.us/search/advanced'
		self._encore['dl'] = 'https://files.enchor.us/'

		self.limit = limit
		self.exact = exact

	def search(self, query: dict) -> dict:
		d = { 'number' : 1, 'page' : 1 }
		for i in query:
			if i == "instrument" or i == "difficulty":
				d[i] =  query[i]
			else:
				d[i] = { 'value' : query[i], 'exact' : self.exact, 'exclude' : False }
		if d['instrument'] == 'drums':#Drum results don't return right w/o this
			d['drumsReviewed'] = False
		resp = self._session.post(self._encore['adv'], data = json.dumps(d))
		return SearchResponse.parse_raw(json.dumps(resp.json()))

	def url(self, chart) -> str:
		return f"{self._encore['dl']}{chart.md5}{('_novideo','')[not chart.has_video_background]}.sng"

	def download_from_chart(self, chart: dict) -> str:
		return io.BytesIO(self._session.get(self.url(chart)).content)

	def download_from_url(self, url: str) -> str:
		return self._session.get(url).content

class CHOpt:
	class Opts:
		whammy: int = 0
		squeeze: int = 0
		speed: int = 100
		lazy: int = 0
		delay: int = 0
		instrument: str = CH_INSTRUMENTS[0][0]
		difficulty: str = CH_DIFFICULTIES[0][0]
		#Do check for tuple force string
	def __init__(self):
		self._path = settings.CHOPT_PATH
		self._chopt = f"{self._path}/CHOpt.exe" if platform.system() == 'Windows' else f"{self._path}/CHOpt"
		self._scratch = f"{self._path}/scratch"
		self._output = settings.CHOPT_OUTPUT
		self._url = settings.CHOPT_URL
		self._encore = EncoreClient()
		self._tmp = ""
		self.opts = self.Opts()
		self.url = ""
		self.img = None
		self.img_path = ""
		self.img_name = ""
		self._delete = True
		self._file_id = uuid.uuid1()

		#Create dirs
		if not os.path.isdir(self._scratch):
			os.makedirs(self._scratch)
		if not os.path.isdir(self._output):
			os.makedirs(self._output)

	def __del__(self):
		if self.img:
			self.img.close()
			if self._delete:
				os.remove(self.img_path)
		if self._tmp != "":
			shutil.rmtree(self._tmp)

	def _prep_chart(self):
		self._tmp = f"{self._scratch}/{self._file_id}"
		os.makedirs(self._tmp)
		if self._sng.is_chart_format:
			with open(f"{self._tmp}/notes.chart", "wb") as f:
				f.write(self._sng.chart)
		else:
			with open(f"{self._tmp}/notes.mid", "wb") as f:
				f.write(self._sng.chart)
		with open(f"{self._tmp}/song.ini", 'wb') as f:
			f.write(self._sng.songini)

	def save_for_upload(self):
		self.img.save(f"{self._output}/{self.img_name}", "PNG")
		self._delete = False

	def gen_path(self, chart: Union[dict, Chart]) -> str:
		if isinstance(chart, Chart):
			if chart.sngfile:
				content = chart.sngfile.open().read()
			else:
				content = self._encore.download_from_url(chart.url)
			self.opts.speed = chart.speed
			self.opts.instrument = chart.instrument
			self.opts.difficulty = chart.difficulty
		else:
			content = self._encore.download_from_url(self._encore.url(chart))
			self.opts.instrument = self.opts.instrument[0]

		self._sng = SNGHandler(content)
		self._prep_chart()
		self._out_png = f"{self._output}/{self._file_id}.png"
		choptCall = f"{self._chopt} -s {self.opts.speed} --ew {self.opts.whammy} --sqz {self.opts.squeeze} -f {self._tmp}/{'notes.chart' if self._sng.is_chart_format else 'notes.mid'} -i {self.opts.instrument} -d {self.opts.difficulty} --lazy {self.opts.lazy} --delay {self.opts.delay} -o {self._out_png}"
		try:
			subprocess.run(choptCall, check=True, shell=True, stdout=subprocess.DEVNULL)
		except Exception as e:
			print(f"CHOPT: died on chart {chart.name}")
			print(f"CHOpt: call failed with exception: {e}")
			return None

		print(f"CHOPT: Output PNG: {self._out_png}")
		self.url = f"{self._url}/{self._file_id}.png"
		self.img_path = self._out_png
		self.img_name = f"{self._file_id}.png"
		return self.url

class Hydra:
	class Opts:
		bass2x: bool = True
		pro: bool = True
		depth_mode: Literal["scores", "points"] = "scores"
		depth: int = 4
		difficulty: CH_DIFFICULTIES = CH_DIFFICULTIES[0]

	def __init__(self):
		self.opts = self.Opts()
		self._encore = EncoreClient()

	def gen_path(self, chart: Union[dict, Chart]):
		if isinstance(chart, Chart):
			content = self._encore.download_from_url(chart.url)
		elif isinstance(chart, dict):
			content = self._encore.download_from_chart(chart)
		sng = SNGHandler(content)
		self._chart = sng
		if self._chart.is_chart_format:
			output = analyze_chart_bytes_chart(self._chart.chart, self.opts.difficulty, self.opts.pro, self.opts.bass2x, self.opts.depth_mode, self.opts.depth)
		else:
			output = analyze_chart_bytes_mid(self._chart.chart, self.opts.difficulty, self.opts.pro, self.opts.bass2x, self.opts.depth_mode, self.opts.depth)

		self.output = [p.pathstring_verbose() for p in output.all_paths()]
		return self.output

class CHStegTool:
	def __init__(self):
		self._path = settings.CHSTEG_PATH
		self._steg = f"{self._path}/ch_steg_reader.exe" if platform.system() == "Windows" else f"{self._path}/ch_steg_reader"
		self._media_root = settings.MEDIA_ROOT
		self._scratch = f"{self._path}/scratch"
		if not os.path.isdir(self._scratch):
			os.makedirs(self._scratch)

		self.img_path = None
		self.img_name = ""
		self.output = None
		self.img = None
		self.delete = True

	def __del__(self):
		if self.delete and self.img:
			os.remove(self.img_path)

	def _get_over_strums(self):
		outStr = pytesseract.image_to_string(self.img)
		osCnt = re.findall("(?<=Overstrums )([O|0-9]+)", outStr)
		for i, cnt in enumerate(osCnt):
			osCnt[i] = cnt.replace('O', '0')
		for i, player in enumerate(self.output.players):
			if len(osCnt) == len(self.output.players) and osCnt[i].isdigit():
				player.excess_hits = int(osCnt[i])
			else:
				player.excess_hits = -1

	async def _prep_image(self, image):
		image.filename = re.sub(r'[^a-zA-Z0-9-_.]', '', image.filename)
		self.img_name = image.filename
		self.img_path = f"{self._scratch}/{image.filename}"
		await image.save(self.img_path, seek_begin=True)
		self.img = Image.open(self.img_path)

	def _sanitize_steg(self, steg: dict):
		steg = StegScreenshot.parse_raw(steg.stdout.decode("utf-8"))
		steg.charter_name = re.sub(r"(?:<[^>]*>)", "", steg.charter_name)
		for ply in steg.players:
			ply.profile_name = re.sub(r"(?:<[^>]*>)", "", ply.profile_name)
		return steg

	def _call_steg(self):
		stegCall = f"{self._steg} --json {self.img_path}"
		try:
			proc = subprocess.run(stegCall.split(), stdout = subprocess.PIPE, stderr = subprocess.PIPE)
			err = proc.stderr.decode('utf-8')
			if proc.returncode == 0 or proc.returncode == '0':
				self.output = self._sanitize_steg(proc)
				if self.output.game_version in "v1.0.0.4080-final":
					self._get_over_strums()
				for i, player in enumerate(self.output.players):
					player.notes_missed = player.total_notes - player.notes_hit
			elif err == 'Error: InvalidScreenshotData\n':
				print(f"STEG: Error - invalid steg data found in image {self.img_name}")
				self.output = None
		except Exception as e:
			print(f"STEG: Call failed: {e}")
			self.output = None

	def getStegInfoSync(self, image) -> dict:
		self.img_name = image
		self.img_path = f"{settings.MEDIA_ROOT}{image}"
		self.delete = False
		self.img = Image.open(self.img_path)
		self._call_steg()
		return self.output

	async def getStegInfo(self, image: discord.Attachment) -> dict:
		await self._prep_image(image)
		self._call_steg()
		return self.output

	def buildStatsEmbed(self, title: str) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = title
		chartStr = f"Chart: `{self.output.artist_name}" + f" - {self.output.song_name}" + (f" ({self.output.playback_speed}%)" if self.output.playback_speed != 100 else '') + f" ({self.output.charter_name})`\n"
		chartStr += f"Run Time: <t:{int(self.output.score_timestamp.timestamp())}:f>\n"
		chartStr += f"Game Version: `{self.output.game_version}`"
		embed.add_field(name="Submission Stats", value=chartStr, inline=False)
		#embed.set_footer(text=f"Chart md5 `{self.output.checksum}`")
		for i, player in enumerate(self.output.players):
			#plyStr = ""
			#plyStr += f"Player Name: `{player.profile_name}`\n"
			plyStr = f"Score: `{player.score}`\n"
			plyStr += f"Notes Hit: `{player.notes_hit}/{player.total_notes} - {(player.notes_hit/player.total_notes) * 100:.2f}% {' - 👑' if player.is_fc else f'(-{player.notes_missed})'}`\n"
			plyStr += f"Overstrums: `(+){player.excess_hits}`\n"
			plyStr += f"Ghosts: `{player.frets_ghosted}`\n"
			plyStr += f"SP Phrases: `{player.sp_phrases_earned}/{player.sp_phrases_total}`\n"
			embed.add_field(name=f"Player: `{player.profile_name}`", value=plyStr, inline=False)
		embed.add_field(name="", value=f"Chart MD5: `{self.output.checksum}`")
		return embed

class GSheets():
	def __init__(self, fin=False):
		self._final = fin
		self._format_border = {'textFormat': {'bold': False}, "horizontalAlignment": "CENTER", 'borders': {'right': {'style' : 'SOLID'}, 'left': {'style' : 'SOLID' }}}
		self._format_header = {'textFormat': {'bold': True}, "horizontalAlignment": "CENTER", 'borders': { 'bottom': { 'style' : 'SOLID' }, 'left': { 'style' : 'SOLID' }, 'right': { 'style' : 'SOLID' }}}

	def login(self):
		gs = GSheetAPI.objects.get()
		self._gc = gspread.service_account_from_dict(gs.api_key, http_client=gspread.BackOffHTTPClient)
		if not self._gc:
			raise RuntimeError("Gsheels API: API Key invalid/failed to login")

	def set_submission(self, submission: Union[Match, QualifierSubmission]):
		self._submission = submission
		if isinstance(self._submission, QualifierSubmission):
			self._tourney = self._submission.qualifier.tournament
			self._bracket = self._submission.qualifier.bracket
			self._url = self._submission.qualifier.gsheet
		elif isinstance(self._submission, Match):
			self._tourney = self._submission.group.bracket.tournament
			self._bracket = self._submission.group.bracket
			self._url = self._tourney.config.gsheet

		try:
			self._sheet = self._gc.open_by_url(self._url)
		except Exception as e:
			print(f"Error opening GSheet {self._url} failed with exception {e}")
			raise e
		#Load relevant workspace in sheet
		if isinstance(self._submission, QualifierSubmission):
			try:
				if not self._final:
					ws = self._sheet.worksheet((f"{self._submission.qualifier} - Data"))
				else:
					ws = self._sheet.worksheet((f"{self._submission.qualifier} - Final Top Scores"))
			except gspread.exceptions.WorksheetNotFound:
				ws = self.setup_qualifier_sheet()
		elif isinstance(self._submission, Match):
			try:
				ws = self._sheet.worksheet((f"{self._submission.tournament.short_name} - Match Data"))
			except gspread.exceptions.WorksheetNotFound:
				ws = self.setup_completed_sheet()

		self._ws = ws

	def setup_qualifier_sheet(self) -> gspread.Worksheet:
		print(f"Creating qualifier {self._submission.qualifier} worksheet in sheet {self._url}")
		if not self._final:
			ws = self._sheet.add_worksheet(title=f"{self._submission.qualifier} - Data", rows=1, cols=12)
		else:
			ws = self._sheet.add_worksheet(title=f"{self._submission.qualifier} - Final Top Scores", rows=1, cols=12)
		ws.update([["Qualifier ID", "Discord Name", "Clone Hero Name", "Score", "Notes Missed", "Notes Hit", "Overstrums", "Ghosts", "Phrases Hit", "Submission Timestamp", "Screenshot Timestamp", "Screenshot", "Game Version" ]], "A1:M1")
		ws.format("A1:M1", self._format_header)
		#ws.freeze("A1:M1")
		#TODO - Add any graphs/viewables that'd be nice to add
		return ws

	def setup_completed_sheet(self) -> bool:
		print(f"Creating Match Air Table {self._submission.tournament} worksheet in sheet {self._url}")
		ws = self._sheet.add_worksheet(title=f"{self._submission.tournament.short_name} - Match Data", rows=1, cols=16)
		ws.update([["Match ID", "Bracket", "Group", "Match", "PickSong", "Song", "Player", "Score", "W/L",  "Notes Missed", "Notes Hit", "Overstrums", "Ghosts", "Phrases Hit", "imestamp", "Screenshot"]], "A1:P1")
		ws.format("A1:P1", self._format_header)
		#ws.freeze("A1:P1")
		#TODO - Add "the live table formatting/formulas for the viewable worksheets
		return ws

	def submit_qualifier(self):
		self._ws.append_row(self.qualifier_line, value_input_option="USER_ENTERED")
		self._submission.submitted = True
		self._submission.save()

	def submit_completed(self) -> bool:
		self._ws.append_rows(self.completed_lines, value_input_option="USER_ENTERED")

	def update_qualifier(self):
		cell = self._ws.find(self._submission.id)
		self._ws.update([self.qualifier_line], f"A{cell.row}:M{cell.row}", raw=False)

	def update_match(self):
		cell = self._ws.find(self._submission.id)
		for i, line in enumerate(self.completed_lines):
			self._ws.update([line], f"A{(cell.row + i)}:P{(cell.row + i)}", raw=False)

	@property
	def qualifier_line(self):
		qid = self._submission.id
		chName = self._submission.steg.players[0].profile_name
		score = self._submission.steg.players[0].score
		missed = self._submission.steg.players[0].notes_missed
		hit = self._submission.steg.players[0].notes_hit
		excess = self._submission.steg.players[0].excess_hits
		ghosts = self._submission.steg.players[0].frets_ghosted
		phrases = self._submission.steg.players[0].sp_phrases_earned
		submissionTimestamp = f"{self._submission.submit_time.strftime("%Y-%m-%d %H:%M:%S")}-UTC"
		screenshotTimestamp = f"{self._submission.steg.score_timestamp.strftime('%Y-%m-%d %H:%M:%S')}-UTC"
		link = f'=HYPERLINK("https://{settings.BASE_URL}{self._submission.screenshot.url}", "Screenshot Link")'
		gameVer = self._submission.qualifier.tournament.config.version
		return [qid, self._submission.player.name, chName, score, missed, hit, excess, ghosts, phrases, submissionTimestamp, screenshotTimestamp, link, gameVer]

	@property
	def completed_lines(self):
		retLines = []
		matchId = self._submission.id
		bracket = str(self._submission.bracket)
		group = str(self._submission.group)
		match = self._submission.short_name
		for rnd in self._submission.rounds:
			for ply in rnd.steg.players:
				picked = str(rnd.picked.ch_name) if rnd.picked else '"Ref"'
				song = rnd.chart.tournament_name
				chName = ply.profile_name
				score = ply.score
				if rnd.winner.check_ch_name(chName):
					wl = "W"
				else:
					wl = "L"
				missed = ply.notes_missed
				hit = ply.notes_hit
				excess = ply.excess_hits
				ghosts = ply.frets_ghosted
				phrases = ply.sp_phrases_earned
				ts = f"{rnd.created.strftime('%Y-%m-%d %H:%M:%S')}-UTC"
				link = f'=HYPERLINK("https://{settings.BASE_URL}{rnd.screenshot.url}", "Screenshot Link")'
				retLines.append([matchId, bracket, group, match, picked, song, chName, score, wl, missed, hit, excess, ghosts, phrases, ts, link])
		return retLines
