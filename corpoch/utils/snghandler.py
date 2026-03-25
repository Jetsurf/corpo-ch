import json, io, hashlib, re, os
from zipfile import ZipFile
from pydantic import BaseModel
from typing import Optional, Union

class SNGHandler:
	def __init__(self, submission: Union[str,bytes], playlist: Union[str,None]=None, sanitize=True):
		if not ((isinstance(submission, bytes) and (submission[:6].decode('utf-8') == "SNGPKG") or submission[:4] == b"\x50\x4B\x03\x04") or
			(os.path.isfile(os.path.join(submission,"song.ini")) and
			(os.path.isfile(os.path.join(submission,"notes.chart")) or os.path.isfile(os.path.join(submission,"notes.mid"))))):
			raise TypeError("Submission must be a directory of a single chart or the bytes of an .sng")
		self._playlist = playlist
		self._sanitize = sanitize

		if isinstance(submission, bytes) and submission[:6].decode('utf-8') == "SNGPKG":
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

			for index, file in enumerate(files):
				if ((file.lower().startswith(valid_picture_names) and file.lower().endswith(valid_picture_extensions)) or
					(file.lower().startswith(valid_music_names) and file.lower().endswith(valid_music_extensions)) or
					(file.lower().startswith(valid_video_names) and file.lower().endswith(valid_video_extensions)) or
					(file.lower() in valid_notes) or
					(file.lower() == valid_songini)):
					if iszip:
						with ZipFile(io.BytesIO(submission), 'r') as zip_file:
							file_bytes = zip_file.read(file_paths[index])
							results.append([file.lower(), file_bytes])
					else:
						with open(os.path.join(submission,file), 'rb') as f:
							file_bytes = f.read()
							results.append([file.lower(), file_bytes])
			chart_present = any(item[0] == 'notes.mid' for item in results)
			if chart_present:
				filtered_list = [item for item in results if item[0] != 'notes.chart']
				self._files = filtered_list
			else:
				self._files = results

	@property
	def outputChartName(self):
		for row in self._files:
			filename = row[0]
			if "song.ini" in filename:
				for line in row[1].decode('utf-8').splitlines():
					subd_line = re.sub("(?:<[^>]*>)", "", line)
					if line.startswith("name"):
						name = subd_line.split('=', 1)[1].strip()
					if line.startswith("artist"):
						artist = subd_line.split('=', 1)[1].strip()
					if line.startswith("charter"):
						charter = subd_line.split('=', 1)[1].strip()
			else:
				continue
		newFile = f"{name}"
		if artist:
			newFile = newFile + " - " + f"{artist}"
		if charter:
			newFile = newFile + " (" + f"{charter}" + ")"
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
	def songini_model(self):
		songini_raw = self.songini.decode('utf-8')
		songini_dict = {}
		for line in songini_raw.splitlines():
			if "=" in line:
				line = line.split('=', 1)
				key = line[0].strip()
				value = line[1].strip()
				if value.strip():
					songini_dict[key] = value
		songini = self.SongIni.model_validate(songini_dict)
		return songini

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

	def parse_metadataPairArray(self, data: bytes) -> list[list[str]]:
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

	def parse_fileMetaArray(self, data: bytes) -> list[list[Union[str, int]]]:
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
				if "=" in line:
					line = line.split('=',1)
					key = line[0].strip()
					value = line[1].strip()
				else:
					continue
				if value:
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

	class SongIni(BaseModel):
		name: str
		artist: Optional[str] = None
		album: Optional[str] = None
		genre: Optional[str] = None
		year: Optional[str] = None
		album_track: Optional[int] = None
		playlist_track: Optional[int] = None
		charter: Optional[str] = None
		icon: Optional[str] = None
		diff_guitar: Optional[int] = None
		diff_rhythm: Optional[int] = None
		diff_bass: Optional[int] = None
		diff_guitar_coop: Optional[int] = None
		diff_drums: Optional[int] = None
		diff_drums_real: Optional[int] = None
		diff_guitarghl: Optional[int] = None
		diff_bassghl: Optional[int] = None
		diff_rhythm_ghl: Optional[int] = None
		diff_guitar_coop_ghl: Optional[int] = None
		diff_keys: Optional[int] = None
		song_length: Optional[int] = None
		preview_start_time: Optional[int] = None
		video_start_time: Optional[int] = None
		delay: Optional[int] = None
		modchart: Optional[bool] = False
		loading_phrase: Optional[str] = None

		class Config:
			populate_by_name = True
