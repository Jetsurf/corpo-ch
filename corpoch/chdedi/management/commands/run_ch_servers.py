import asyncio, atexit, json, os, pprint, psutil, re, signal, sys, time
from contextlib import chdir

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from subprocess_monitor import SubprocessMonitor

from corpoch.chdedi.models import CHDediServer, GlobalConfig

class CHManager:
	def __init__(self, servers, skip_startup):
		self._skip_startup = skip_startup
		os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
		self._monitor = SubprocessMonitor(check_interval=10)
		self._servers = servers
		signal.signal(signal.SIGINT, self.sig_term)
		self.listeners = set()

	def __del__(self):
		self.global_config.pid = None
		self.global_config.save()

	@property
	def global_config(self):
		return GlobalConfig.objects.get()

	def sig_term(self, sig, frame):
		print("Keyboard Interrput, exiting.")

		sys.exit(0)

	async def run(self, server):
		print(f"Starting CH Server: {server}")
		with chdir(server.path):
			try:
				settings = server.write_settings()
			except Exception as e:
				print(f"Exception writing settings for {server} - stopping: {e}")
				server.pid = None
				server.global_config.to_stop.add(server)
				return

			server.players = 0 #Ensure count is 0 on start
			server.pid = await self._monitor.start_subprocess({ "cmd" : server.exec_str, "args" : [] })
			time.sleep(2) #Give binary chance to start

			with open("server.log", "r") as log:
				for line in log:
					if "Game Version: " in line:
						server.version = line.split()[5]
						print(f"[{server}] - CH Version: {server.version}")
						break

			#Force players/spectators to 0/default
			server.players = 0
			server.spectators = 0

			#If CH binary > 1.1 6161 w/ udp message support
			if server.udp_listener != 0 and int(server.version.split(".")[3].split('-')[0]) >= 6161:
				try:
					loop = asyncio.get_event_loop()
					listener = loop.create_datagram_endpoint(lambda: CHReader(server), local_addr=(server.udp_listener.udp_events_host, server.port))
					loop.create_task(listener)
					self.listeners.add(listener)
					print(f"[{server}] - Setup listener on port {server.udp_listener.udp_events_port}")
				except Exception as e: #Catch socket creation errors
					print(f"Got exception starting udp listener: {e}")

				#Force set scene to default
				server.scene = "Lobby"
			else:
				server.scene = "Ver < 1.1.0-6161 - Not Supported"

			await server.asave()

	async def restart(self, server):
		await self.stop(server)
		await self.run(server)

	async def main(self):
		asyncio.create_task(self._monitor.run())
		if not self._skip_startup:
			for server in self._servers:
				if server.pid and psutil.pid_exists(server.pid):
					print(f"Reattaching to {server} {server.pid}")
					process = psutil.Process(server.pid)
					process.returncode = None
					self._monitor.process_ownership[server.pid] = process
				else:
					await self.run(server)
		while True:
			close_old_connections()
			async for server in self.global_config.to_restart.all():
				await self.restart(server)
				self.global_config.to_restart.remove(server)
				await self.global_config.asave()
			async for server in self.global_config.to_stop.all():
				await self.stop(server)
				self.global_config.to_stop.remove(server)
				await self.global_config.asave()

			await asyncio.sleep(5)

	async def stop(self, server):
		print(f"Stopping CH Server: {server}")
		try:
			parent = psutil.Process(server.pid)
			for child in parent.children(recursive=True):
				child.terminate()

		except psutil.NoSuchProcess:
			print(f"Server {server} {server.pid} not running. Checking for zombies")
			for proc in psutil.process_iter():
				procStr = proc.name()
				if proc.name() in server.process_name:
					try:
						if server.path in proc.exe():
							print(f"Killed zombie server {proc.exe()}")
							proc.terminate()
					except psutil.AccessDenied:
						continue
			server.pid = None
			await server.asave()

class CHReader(asyncio.DatagramProtocol):

	def __init__(self, server):
		self.server = server
		super().__init__()

	def connection_made(self, transport):
		self.transport = transport

	def datagram_received(self, data, addr):
		raw = data.decode('utf8').replace("'", '"')
		try:
			message = json.loads(raw)
		except Exception as e:
			print(f"Invalid message received, exception: {e} - message:")
			pprint.pprint(raw)
			return

		if 'player_' in message['event']:
			print(f"[{message['ts']}][{self.server}] - Player count now {message['player_count']}")
			if message['spectator']:
				if 'join' in message['event']:
					self.server.spectators += 1
				else:
					self.server.spectators -= 1
			else:
				self.server.players = message['player_count']
			self.server.save()
		elif 'kind' in message and message['kind'] == 'SystemMessage':
			print(f"[{message['ts']}][{self.server}] - System Message: {message['message']}")
		elif 'scene_change' in message['event']:
			print(f"[{message['ts']}][{self.server}] - Scene Change: {message['scene']}")
			self.server.scene = message['scene']
			self.server.save()
		elif 'chat' == message['event']:
			player_name = re.sub(r"(?:<[^>]*>)", "", message['name'])
			print(f"[{message['ts']}][{self.server}] - Chat: {player_name} : {message['message']}")
		else:
			print(f"[{message['ts']}][{self.server}] - Raw Message")
			pprint.pprint(message)

class Command(BaseCommand):
	help = 'Run CH Dedicated Servers'

	def add_arguments(self, parser):
		parser.add_argument('-s', '--skip-startup', action="store_true", help='Starts monitor without starting servers')

	def handle(self, *args, **options):
		sys.stdout.reconfigure(line_buffering = True)
		sys.stderr.reconfigure(line_buffering = True)
		print("Starting Clone Hero Dedicated Servers")
		conf = GlobalConfig.objects.get()
		conf.pid = os.getpid()
		conf.save()
		mgr = CHManager(CHDediServer.objects.all(), options['skip_startup'])
		asyncio.run(mgr.main())
