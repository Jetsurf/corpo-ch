import requests, json, struct, io, hashlib

from corpoch import __user_agent__

class EncoreClient:
	def __init__(self, raw_search: bool=False, limit_results: bool=False):
		self._session = requests.Session()
		self._session.headers = {
			'User-Agent' : __user_agent__,
			"Content-Type": "application/json"
		}
		# encore.us API urls
		self._encore={}
		self._encore['gen'] = 'https://api.enchor.us/search'
		self._encore['adv'] = 'https://api.enchor.us/search/advanced'
		self._encore['dl'] = 'https://files.enchor.us/'

		self.limit_results = limit_results
		self.raw_search = raw_search

	def search(self, query: dict) -> dict:
		d = { 'number' : 1, 'page' : 1 }

		for i in query:
			d[i] = { 'value' : query[i], 'exact' : True, 'exclude' : False }

		print(f"d: {d}")
		resp = self._session.post(self._encore['adv'], data = json.dumps(d))
		print(f"Resp {resp.text}")
		#remove dupelicate chart entries from search
		theJson = resp.json()['data']
		for i, chart1 in enumerate(theJson):
			for j, chart2 in enumerate(theJson):
				if chart1['ordering'] == chart2['ordering'] and i != j:
					del theJson[j]

		#print(json.dumps(theJson, indent=4))
		if self.raw_search:
			retData = theJson
		else:
			retData = []
			atts = ['name','artist','md5','charter','album','hasVideoBackground']
			for i, v in enumerate(theJson):
				if i > 10 and self.limit_results:
					break

				s = {}
				d = theJson[i]
				for j in atts:
					s[j] = d[j]

			retData.append(s)

		return retData

	def url(self, encoreChart: dict) -> str:
		print(f"Chart: {encoreChart}")
		print(f"URL: { f"{self._encore['dl']}{encoreChart['md5']}{('_novideo','')[not encoreChart['hasVideoBackground']]}.sng"}")
		return f"{self._encore['dl']}{encoreChart['md5']}{('_novideo','')[not encoreChart['hasVideoBackground']]}.sng"

	def download(self, encoreChart: dict) -> str:
		print("DEBUG: Called Download")
		return self._session.get(self.url(encoreChart)).content

	#Big shoutout to @mirjay for this until they actually get a proper collaborator role on the project
	#Move these to a separate .sng provider class?
	def parse_fileMetaArray(self, data, metaData=False) -> dict:
		print("DEBUG: Called fileMetaArray")
		byte_stream = io.BytesIO(data)
		while True:
			filenameLen_bytes = byte_stream.read(1)
			filenameLen = int.from_bytes(filenameLen_bytes, byteorder='little')
			
			filename_bytes = byte_stream.read(filenameLen)
			filename = filename_bytes.decode('utf-8').casefold()
				
			contentsLen_bytes = byte_stream.read(8)
			contentsLen = int.from_bytes(contentsLen_bytes, byteorder='little')
			
			contentsIndex_bytes = byte_stream.read(8)
			contentsIndex = int.from_bytes(contentsIndex_bytes, byteorder='little')
			print(f'name {filename}')
			if "notes.chart" in filename or "notes.mid" in filename and metaData:
				print("DEBUG: File Meta Array returning")
				return {"Index" : contentsIndex, "Length" : contentsLen}
			elif 'song.ini' in filename and metaData:
				return {"Index" : contentsIndex, "Length" : contentsLen}

	def get_md5(self, encoreChart: dict) -> str:
		all_bytes = self.download(encoreChart)
		print("DEBUG: Got Download")
		all_bytes_stream = io.BytesIO(all_bytes)
		all_bytes_stream.seek(10)
		
		xor_mask_bytes = all_bytes_stream.read(16)
		xorMask = list(xor_mask_bytes)

		metadataLen_bytes = all_bytes_stream.read(8)
		metadataLen = int.from_bytes(metadataLen_bytes, byteorder='little', signed=False)
		
		all_bytes_stream.seek(metadataLen, 1)
		
		fileMetaLen_bytes = all_bytes_stream.read(8)
		fileMetaLen = int.from_bytes(fileMetaLen_bytes, byteorder='little', signed=False)

		all_bytes_stream.seek(8, 1)

		fileMetaArray_bytes = all_bytes_stream.read(fileMetaLen-8)
		fileMetaArray = self.parse_fileMetaArray(fileMetaArray_bytes)

		fileDataLen_bytes = all_bytes_stream.seek(8, 1)

		all_bytes_stream.seek(fileMetaArray['Index'])
		file_Chart_bytes = all_bytes_stream.read(fileMetaArray['Length'])
		file_Chart_bytes_array = list(file_Chart_bytes)
		fileMetaArray 
		unmasked_file_Chart_bytes = [None] * len(file_Chart_bytes_array)
		print("Doing for loop")
		for i in range(len(file_Chart_bytes_array)):
			xorKey = xorMask[i % 16] ^ (i % 256)
			unmasked_file_Chart_bytes[i] = file_Chart_bytes_array[i] ^ xorKey
		md5 = hashlib.md5(bytes(unmasked_file_Chart_bytes)).hexdigest()
		print(f"Got md5 {md5}")
		return md5

class SngCli:
	def __init__(self):
		# SngCli Converter
		self._path = 'SngCli/SngCli.exe' if platform.system() == 'Windows' else 'SngCli/SngCli'
		self._input = 'SngCli/input'
		self._output = 'SngCli/output'

class CHOpt:
	def __init__(self):
		self._path = 'CHOpt/CHOpt.exe' if platform.system() == 'Windows' else 'CHOpt/CHOpt'
