import typing, requests_cache, json, io, hashlib, re, gspread, asyncio, discord, os, uuid, platform, subprocess, pytesseract, shutil
from zipfile import ZipFile
from datetime import datetime
from typing import Union
from random import randbytes
from PIL import Image, ImageEnhance
from django.db import models

from corpoch import __user_agent__
from corpoch import settings
from corpoch.models import GSheetAPI, Chart, Tournament, TournamentMatchCompleted, TournamentMatchOngoing, Qualifier, QualifierSubmission, CH_DIFFICULTIES, CH_INSTRUMENTS
from corpoch.utils.hydra.hydra.hyutil import analyze_chart_bytes_chart, analyze_chart_bytes_mid
from corpoch.types import StegScreenshot

class SNGHandler:
	def __init__(self, submission: Union[str,bytes], playlist: str=None, sanitize=True):
		if not ((isinstance(submission, bytes) and (submission[:6].decode('utf-8') == "SNGPKG") or submission[:4] == b"\x50\x4B\x03\x04") or
			(os.path.isfile(os.path.join(submission,"song.ini")) and
			(os.path.isfile(os.path.join(submission,"notes.chart")) or os.path.isfile(os.path.join(submission,"notes.mid"))))):
			raise TypeError("Submission must be a directory of a single chart or the bytes of an .sng")
		self._playlist = playlist
		self._sanitize = sanitize

		if isinstance(submission, bytes):
			self._files = self.get_sng_files(submission)
		else:
			if isinstance(submission, bytes) and submission[:4] == b"\x50\x4B\x03\x04":
				iszip = True
				with ZipFile(io.BytesIO(submission), 'r') as zip_file:
					all_files = zip_file.namelist()

					containing_paths = []
					for file_path in all_files:
						if file_path.lower().endswith('song.ini'):
							if file_path == 'song.ini':
								dir_path = ""
							else:
								dir_path = file_path.rsplit('/',1)[0]
							containing_paths.append(dir_path)

					target_dir = min(containing_paths,key=len)
					if target_dir == "":
						files = [f.lower() for f in all_files if "/" not in f and f != ""]
						file_paths = [f for f in all_files if "/" not in f and f != ""]
					else:
						files = [f.lower().split('/')[-1] for f in all_files if f.startswith(target_dir + "/") and "/" not in f.split(target_dir+"/")[1] and f.split('/')[-1] != "" ]
						file_paths = [f for f in all_files if f.startswith(target_dir + "/") and "/" not in f.split(target_dir+"/")[1] and f.split('/')[-1] != "" ]

			else:
				iszip = False
				files = os.listdir(submission)

			results = []

			valid_picture_names = ("album.","background.","highway.")
			valid_picture_extensions = ("png","jpg","jpeg")
			valid_music_names = ("guitar.","bass.","rhythm.","vocals.","vocals_1.","vocals_2.","drums.","drums_1.","drums_2.","drums_3.","drums_4.","keys.","song.","crowd.","preview.")
			valid_music_extensions = ("mp3","ogg","opus","wav")
			valid_video_names = ("video.")
			valid_video_extensions = ("mp4","avi","webm","vp8","ogv","mpeg")
			valid_notes = ["notes.chart","notes.mid"]
			valid_songini = "song.ini"

			for file in files:
				if ((file.lower().startswith(valid_picture_names) and file.lower().endswith(valid_picture_extensions)) or
					(file.lower().startswith(valid_music_names) and file.lower().endswith(valid_music_extensions)) or
					(file.lower().startswith(valid_video_names) and file.lower().endswith(valid_video_extensions)) or
					(file.lower() in valid_notes) or
					(file.lower() == valid_songini)):
					if iszip:
						with ZipFile(io.BytesIO(submission), 'r') as zip_file:
							file_bytes = zip_file.read(file_paths[index])
							results.append([file, file_bytes])
					else:
						with open(os.path.join(submission,file), 'rb') as f:
							file_bytes = f.read()
							results.append([file.lower(), file_bytes])
			self._files = results

	@property
	def outputChartName(self):
		for row in self._files:
			if "song.ini" in row[0]:
				for line in row[1].decode('utf-8'):
					subd_line = re.sub("(?:<[^>]*>)", "", line)
					if line.startswith("name"):
						name = subd_line.split('=', 1)[1]
					if line.startswith("artist"):
						artist = subd_line.split('=', 1)[1]
					if line.startswith("charter"):
						charter = subd_line.split('=', 1)[1]
		newFile = f"{artist} - {name} ({charter})"
		newFile = newFile.replace("/",  u'\uFF0F') #／
		newFile = newFile.replace("\\", u'\u29F5') #⧵
		newFile = newFile.replace(":",  u'\uA789') #꞉
		newFile = newFile.replace("<",  u'\u276E') #❮
		newFile = newFile.replace(">",  u'\u276F') #❯
		newFile = newFile.replace("\"", u'\u0027') #'
		newFile = newFile.replace("?",  u'\uFF1F') #？
		newFile = newFile.replace("*",  u'\u204E') #⁎
		newFile = newFile.replace("|",  u'\u23D0') #⏐
		newFile = newFile.strip()

		encoding = 'utf-8'
		bytes_data = newFile.encode(encoding)
		sliced_bytes = bytes_data[:255]
		newFile = sliced_bytes.decode(encoding, errors='ignore')
		newFile = newFile.rstrip()

		return newFile

	@property
	def songini(self) -> bytes:
		for row in self._files:
			filename = row[0]
			if "song.ini" in filename:
				if self._sanitize:
					row[1] = re.sub(b"(?:<[^>]*>)", b"", row[1])
				return row[1]

	@property
	def chart(self) -> bytes:
		for row in self._files:
			filename = row[0]
			if "notes.chart" in filename or "notes.mid" in filename:
				return row[1]

	@property
	def is_chart_format(self) -> bool:
		for row in self._files:
			if "notes.chart" in row[0]:
				return True
		return False

	@property
	def md5(self) -> str:
		return hashlib.md5(self.chart).hexdigest()

	def parse_metadataPairArray(self, data: bytes) -> list[list[str, str]]:
		results = []
		byte_stream = io.BytesIO(data)
		while True:
			keyLen_bytes = byte_stream.read(4)
			if not keyLen_bytes:
				break
			keyLen = int.from_bytes(keyLen_bytes, byteorder='little')
			
			key_bytes = byte_stream.read(keyLen)
			key = key_bytes.decode('utf-8')
			
			valueLen_bytes = byte_stream.read(4)
			valueLen = int.from_bytes(valueLen_bytes, byteorder='little')
			
			value_bytes = byte_stream.read(valueLen)
			value = value_bytes.decode('utf-8')
			
			results.append([key, value])
		return results

	def parse_fileMetaArray(self, data: bytes) -> list[list[str, int, int]]:
		results = []
		byte_stream = io.BytesIO(data)
		while True:
			filenameLen_bytes = byte_stream.read(1)
			if not filenameLen_bytes:
				break
			filenameLen = int.from_bytes(filenameLen_bytes, byteorder='little')
			
			filename_bytes = byte_stream.read(filenameLen)
			filename = filename_bytes.decode('utf-8').casefold()
				
			contentsLen_bytes = byte_stream.read(8)
			contentsLen = int.from_bytes(contentsLen_bytes, byteorder='little')
			
			contentsIndex_bytes = byte_stream.read(8)
			contentsIndex = int.from_bytes(contentsIndex_bytes, byteorder='little')
			
			results.append([filename, contentsLen, contentsIndex])
		return results
			
	def xorMask(self, dataArray: list[int], xorMask:list[int]) -> list[int]:
		unmasked_file_bytes = [None] * len(dataArray)
		for i in range(len(dataArray)):
			xorKey = xorMask[i % 16] ^ (i % 256)
			unmasked_file_bytes[i] = dataArray[i] ^ xorKey
		return unmasked_file_bytes

	#Meant to be fed in raw content - this may be able to be improved?
	def get_sng_files(self, all_bytes: bytes) -> list[list[str, bytes]]:
		all_bytes_stream = io.BytesIO(all_bytes)
		all_bytes_stream.seek(10)
		
		xor_mask_bytes = all_bytes_stream.read(16)
		xorMask = list(xor_mask_bytes)

		metadataLen_bytes = all_bytes_stream.read(8)
		metadataLen = int.from_bytes(metadataLen_bytes, byteorder='little', signed=False)
		
		all_bytes_stream.seek(8,1)
		
		metadataPairArray_bytes = all_bytes_stream.read(metadataLen-8)
		metadataPairArray = self.parse_metadataPairArray(metadataPairArray_bytes)
		
		fileMetaLen_bytes = all_bytes_stream.read(8)
		fileMetaLen = int.from_bytes(fileMetaLen_bytes, byteorder='little', signed=False)

		all_bytes_stream.seek(8, 1)

		fileMetaArray_bytes = all_bytes_stream.read(fileMetaLen-8)
		fileMetaArray = self.parse_fileMetaArray(fileMetaArray_bytes)

		results = []
		with io.BytesIO() as songini_stream:
			songini_stream.write(bytes(f"[song]\n".encode('utf-8')))
			for row in metadataPairArray:
				line = f"{row[0]} = {row[1]}\n"
				songini_stream.write(line.encode('utf-8'))
			results.append(["song.ini", songini_stream.getvalue()])
			
		for row in fileMetaArray:
			all_bytes_stream.seek(row[2])
			results.append([row[0],bytes(self.xorMask(list(all_bytes_stream.read(row[1])),xorMask))])
			
		return results
	
	def build_sng(self) -> bytes:
		with io.BytesIO() as sng_stream:
			header ="SNGPKG"
			sng_stream.write(bytes(header.encode('utf-8')))
			version = 1
			sng_stream.write(version.to_bytes(4, byteorder="little"))
			xorMask = randbytes(16)
			sng_stream.write(xorMask)

			metadataPairArray = []
			for row in self._files:
				filename = row[0].lower()
				if "song.ini" in filename:
					songini_bytes = row[1]
			songini_text = songini_bytes.decode('utf-8').split('\n',1)[-1]
			for line in songini_text.strip().split('\n'):
				line = line.split('=',1)
				key = line[0].strip()
				value = line[1].strip()
				metadataPairArray.append([key,value])
			if "playlist" not in metadataPairArray[0] and self._playlist is not None:
				metadataPairArray.append(["playlist",self._playlist])
			with io.BytesIO() as songini_stream:
				for row in metadataPairArray:
					if "playlist" == row[0] and self._playlist is not None:
						key = bytes("playlist".encode('utf-8'))
						keyLen = len(key).to_bytes(4, byteorder="little",signed=True)
						value = bytes(self._playlist.encode('utf-8'))
						valueLen = len(value).to_bytes(4, byteorder='little',signed=True)
						songini_stream.write(keyLen)
						songini_stream.write(key)
						songini_stream.write(valueLen)
						songini_stream.write(value)	
						continue
					key = bytes(row[0].encode('utf-8'))
					keyLen = len(key).to_bytes(4, byteorder="little",signed=True)
					value = bytes(row[1].encode('utf-8'))
					valueLen = len(value).to_bytes(4, byteorder='little',signed=True)
					songini_stream.write(keyLen)
					songini_stream.write(key)
					songini_stream.write(valueLen)
					songini_stream.write(value)
				metadataLen = (8+songini_stream.getbuffer().nbytes).to_bytes(8, byteorder='little',signed=False)
				metadataCount = len(metadataPairArray).to_bytes(8, byteorder='little',signed=False)
				sng_stream.write(metadataLen)
				sng_stream.write(metadataCount)
				sng_stream.write(songini_stream.getvalue())
			
			fileCount = len(self._files)-1
			fileMetaLen = 8 + (17)*fileCount
			for row in self._files:
				if "song.ini" == row[0]:
					continue
				fileMetaLen += len(bytes(row[0].encode('utf-8')))
			sng_stream.write(fileMetaLen.to_bytes(8, byteorder='little', signed=False))
			sng_stream.write(fileCount.to_bytes(8, byteorder='little' ,signed=False))

			fileDataArray_index = sng_stream.getbuffer().nbytes + fileMetaLen
			fileDataArray_Array =[]
			with io.BytesIO() as fileMeta_stream:
				for row in self._files:
					if "song.ini" == row[0]:
						continue
					filename = bytes(row[0].lower().encode('utf-8'))
					filenameLen = len(filename).to_bytes(1, byteorder="little",signed=False)
					contentsLen = len(row[1]).to_bytes(8, byteorder='little',signed=False)
					contentsIndex = (fileDataArray_index).to_bytes(8, byteorder='little',signed=False)
					fileMeta_stream.write(filenameLen)
					fileMeta_stream.write(filename)
					fileMeta_stream.write(contentsLen)
					fileMeta_stream.write(contentsIndex)
					fileDataArray_Array.append([row[0], len(row[1]), fileDataArray_index])
					fileDataArray_index += len(row[1])
				sng_stream.write(fileMeta_stream.getvalue())
			
			fileDataLen = 0
			for row in fileDataArray_Array:
				fileDataLen += row[1]
			sng_stream.write((fileDataLen).to_bytes(8, byteorder='little',signed=False))

			for row in self._files:
				if "song.ini" == row[0].lower():
					continue
				sng_stream.write(bytes(self.xorMask(list(row[1]),xorMask)))

			return sng_stream.getvalue()

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
		if "blake3" in query:
			blake3 = query.pop('blake3')
		else:
			blake3 = None

		for i in query:
			if i == "instrument" or i == "difficulty":
				d[i] =  query[i]
			else:
				d[i] = { 'value' : query[i], 'exact' : self.exact, 'exclude' : False }
		if d['instrument'] == 'drums':#Drum results don't return right w/o this
			d['drumsReviewed'] = False
		resp = self._session.post(self._encore['adv'], data = json.dumps(d))
		#print(f"DEBUG: resp: {resp} text: {resp.text}\nQuery{d}")
		#print(f"Query: {d}")
		theJson = resp.json()['data']
		#print(json.dumps(theJson, indent=4))
		#remove dupelicate chart entries from search
		for i, chart1 in enumerate(theJson):
			for j, chart2 in enumerate(theJson):
				if chart1['ordering'] == chart2['ordering'] and i != j:
					del theJson[j]

		retData = []
		atts = ['name', 'artist','md5','charter','album','hasVideoBackground', 'icon']
		for i, v in enumerate(theJson):
			if i > self.limit:
				break
			if blake3 != None and blake3 not in v['md5'].upper():
				continue

			s = {}
			d = theJson[i]
			for j in atts:
				s[j] = d[j]
			retData.append(s)

		return retData

	def url(self, chart: dict) -> str:
		return f"{self._encore['dl']}{chart['md5']}{('_novideo','')[not chart['hasVideoBackground']]}.sng"

	def download_from_chart(self, chart: dict) -> str:
		return self._session.get(self.url(chart)).content

	def download_from_url(self, url: str) -> str:
		return self._session.get(url).content

	def get_md5_from_chart(self, chart) -> str:
		return SNGHandler(self.download_from_chart(chart)).md5

	def get_md5_from_url(self, url) -> str:
		return SNGHandler(self.download_from_url(url)).md5

class CHOpt:
	class Opts:
		whammy: int = 0
		squeeze: int = 0
		speed: int = 100
		lazy: int = 0
		delay: int = 0
		instrument: CH_INSTRUMENTS = CH_INSTRUMENTS[0]
		difficulty: CH_DIFFICULTIES = CH_DIFFICULTIES[0]

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

	def gen_path(self, chart: typing.Union[dict, Chart]) -> str:
		if isinstance(chart, Chart):
			content = self._encore.download_from_url(chart.url)
			chartName = chart.name
			self.opts.speed = chart.speed
			self.opts.instrument = chart.instrument
		elif isinstance(chart, dict):
			content = self._encore.download_from_chart(chart)
			chartName = chart['name']

		self._sng = SNGHandler(content)
		self._prep_chart()
		self._out_png = f"{self._output}/{self._file_id}.png"
		choptCall = f"{self._chopt} -s {self.opts.speed} --ew {self.opts.whammy} --sqz {self.opts.squeeze} -f {self._tmp}/{'notes.chart' if self._sng.is_chart_format else 'notes.mid'} -i {self.opts.instrument} -d {self.opts.difficulty[0]} --lazy {self.opts.lazy} --delay {self.opts.delay} -o {self._out_png}"
		try:
			subprocess.run(choptCall, check=True, shell=True, stdout=subprocess.DEVNULL)
		except Exception as e:
			print(f"CHOpt call failed with exception: {e}")

		try:
			self.img = Image.open(self._out_png)
		except:
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
		depth_mode: typing.Literal["scores", "points"] = "scores"
		depth: int = 4
		difficulty: CH_DIFFICULTIES = CH_DIFFICULTIES[0]

	def __init__(self):
		self.opts = self.Opts()
		self._encore = EncoreClient()

	def gen_path(self, chart: typing.Union[dict, Chart]):
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
		#print(f"OS Counts: {osCnt}")
		img = Image.open(self.img_path)
		osImg = img.crop((0, 690, 1080, 727))
		outStr = pytesseract.image_to_string(osImg)
		osCnt = re.findall("(?<=Overstrums )([Oo0-9]+)", outStr)
		#Sanity check OS's before adding
		for i, player in enumerate(self.output.players):
			## TODO: THIS NEEDS TO BE FIXED FOR ACTUAL ROUND DATA INFO
			if len(osCnt) == len(self.output.players):
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
				print(f"STEG: Error - invalid no steg data found in image {self.img_name}")
				self.output = None
		except Exception as e:
			print(f"STEG: Call failed: {e}")
			self.output = None

	def getStegInfoSync(self, image) -> dict:
		self.img_name = image
		self.img_path = f"{settings.MEDIA_ROOT}{image}"
		self.delete = False
		self._call_steg()
		return self.output

	async def getStegInfo(self, image: discord.Attachment) -> dict:
		await self._prep_image(image)
		self._call_steg()
		return self.output

	def buildStatsEmbed(self, title: str) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = title
		chartStr = f"Chart Name: {self.output.song_name}" + f" ({self.output.playback_speed}%)\n" if self.output.playback_speed != 100 else '\n'
		chartStr += f"Run Time: <t:{self.output.score_timestamp}:f>\n"
		chartStr += f"Game Version: {self.output.game_version}"
		embed.add_field(name="Submission Stats", value=chartStr, inline=False)
		embed.set_footer(text=f"Chart md5 {self.output.checksum}")
		for i, player in enumerate(self.output.players):
			plyStr = ""
			plyStr += f"Player Name: {player.profile_name}\n"
			plyStr += f"Score: {player.score}\n"
			plyStr += f"Notes Hit: {player.notes_hit}/{player.total_notes} - {(player.notes_hit/player.total_notes) * 100:.2f}% {' - 👑' if player.is_fc else f'(-{player.notes_missed})'}\n"
			plyStr += f"Overstrums: (+){player.excess_hits}\n"
			plyStr += f"Ghosts: {player.frets_ghosted}\n"
			plyStr += f"SP Phrases: {player.sp_phrases_earned}/{player.sp_phrases_total}\n"
			embed.add_field(name=f"Player {i+1}", value=plyStr, inline=False)

		return embed

class GSheets():
	def __init__(self):	
		self._format_border = {'textFormat': {'bold': False}, "horizontalAlignment": "CENTER", 'borders': {'right': {'style' : 'SOLID'}, 'left': {'style' : 'SOLID' }}}
		self._format_header = {'textFormat': {'bold': True}, "horizontalAlignment": "CENTER", 'borders': { 'bottom': { 'style' : 'SOLID' }, 'left': { 'style' : 'SOLID' }, 'right': { 'style' : 'SOLID' }}}

	def login(self):
		gs = GSheetAPI.objects.get()
		self._gc = gspread.service_account_from_dict(gs.api_key)
		if not self._gc:
			raise RuntimeError("Gsheels API: API Key invalid/failed to login")

	def set_submission(self, submission: typing.Union[TournamentMatchOngoing, TournamentMatchCompleted, Qualifier]):
		self._submission = submission
		if isinstance(self._submission, QualifierSubmission):
			self._tourney = self._submission.qualifier.tournament
			self._bracket = self._submission.qualifier.bracket
			self._url = self._submission.qualifier.gsheet
		elif isinstance(self._submission, TournamentMatchOngoing):
			self._tourney = self._submission.group.bracket.tournament
			self._bracket = self._submission.group.bracket
			self._url = self._tourney.config.gsheet
		elif isinstance(self._submission, TournamentMatchCompleted):
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
				ws = self._sheet.worksheet((f"{self._submission.qualifier} - Data"))
			except gspread.exceptions.WorksheetNotFound:
				ws = self.setup_qualifier_sheet()
		elif isinstance(self._submission, TournamentMatchOngoing):
			try:
				ws = self._sheet.worksheet((f"{self._submission.tournament.short_name} - Live Data"))
			except gspread.exceptions.WorksheetNotFound:
				ws = self.setup_ongoing_sheet()
		elif isinstance(self._submission, TournamentMatchCompleted):
			try:
				ws = self._sheet.worksheet((f"{self._submission.tournament.short_name} - Match Data"))
			except gspread.exceptions.WorksheetNotFound:
				ws = self.setup_completed_sheet()

		self._ws = ws

	def setup_qualifier_sheet(self) -> gspread.Worksheet:
		print(f"Creating qualifier {self._submission.qualifier} worksheet in sheet {self._url}")
		ws = self._sheet.add_worksheet(title=f"{self._submission.qualifier} - Data", rows=1, cols=12)
		ws.update([["Discord Name", "Clone Hero Name", "Score", "Notes Missed", "Notes Hit", "Overstrums", "Ghosts", "Phrases Earned", "Submission Timestamp", "Screenshot Timestamp", "Image URL", "Game Version" ]], "A1:L1")
		ws.format("A1:L1", self._format_header)
		return ws

	def setup_ongoing_sheet(self) -> bool:
		pass

	def setup_completed_sheet(self) -> bool:
		pass

	def submit_completed(self) -> bool:
		self._ws.append_rows(self.completed_lines)

	def submit_ongoing(self) -> bool:
		pass

	def submit_qualifier(self):
		self._ws.append_row(self.qualifier_line)
		self._submission.submitted = True
		self._submission.save()

	#worksheet.update([['=SUM(A1:A4)']], 'A5', raw=False)

	@property
	def qualifier_line(self):
		chName = self._submission.steg.players[0].profile_name
		score = self._submission.steg.players[0].score
		missed = self._submission.steg.players[0].notes_missed
		hit = self._submission.steg.players[0].notes_hit
		excess = self._submission.steg.players[0].excess_hits
		ghosts = self._submission.steg.players[0].frets_ghosted
		phrases = self._submission.steg.players[0].sp_phrases_earned
		submissionTimestamp = f"{self._submission.submit_time.strftime("%Y-%m-%d %H:%M:%S")}-UTC"
		screenshotTimestamp = f"{self._submission.steg.score_timestamp.strftime('%Y-%m-%d %H:%M:%S')}-UTC"
		imgUrl = f"https://{settings.BASE_URL}{self._submission.screenshot.url}"
		gameVer = self._submission.qualifier.tournament.config.version
		return [self._submission.player.name, chName, score, missed, hit, excess, ghosts, phrases, submissionTimestamp, screenshotTimestamp, imgUrl, gameVer]

	@property
	def ongoing_lines(self):
		pass

	@property
	def completed_lines(self):
		retLines = []
		matchId = self._submission.id
		bracket = str(self._submission.bracket)
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
				ts = f"{rnd.steg.score_timestamp.strftime('%Y-%m-%d %H:%M:%S')}-UTC"
				url = f"https://{settings.BASE_URL}{rnd.screenshot.url}"
				retLines.append([matchId, bracket, match, picked, song, chName, score, wl, missed, hit, excess, ghosts, phrases, ts, url])
		return retLines


#Keeping for future OCR use/reference
#OCR Tweaking - Keep until v6 is dead
#img = Image.open(imageName)
#image = cv2.imread(imageName)
#gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#blur = cv2.GaussianBlur(gray, (3,3), 0)
#thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
# Morph open to remove noise and invert image
#kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
#opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
#invert = 255 - opening
