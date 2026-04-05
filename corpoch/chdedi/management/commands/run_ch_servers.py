import asyncio, atexit, os, psutil, signal, sys
from contextlib import chdir

from django.core.management.base import BaseCommand

from subprocess_monitor import SubprocessMonitor

from corpoch.chdedi.models import CHDediServer, GlobalConfig

class CHManager:
	def __init__(self, servers, skip_startup):
		self._skip_startup = skip_startup
		os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
		self._monitor = SubprocessMonitor(check_interval=10)
		self._servers = servers
		signal.signal(signal.SIGINT, self.sig_term)

	def __del__(self):
		for server in self._servers:
			server.pid = None
			server.save()

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
			settings = server.write_settings()
			server.pid = await self._monitor.start_subprocess({ "cmd" : server.exec_str, "args" : [] })
			await server.asave()

	async def restart(self, server):
		await self.stop(server)
		await self.run(server)

	async def main(self):
		asyncio.create_task(self._monitor.run())
		if not self._skip_startup:
			for server in self._servers:
				if server.pid:
					await self.stop(server)
				await self.run(server)

		while True:
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
			#parent.terminate()
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

class Command(BaseCommand):
	help = 'Run Corpoch Dbot'

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
