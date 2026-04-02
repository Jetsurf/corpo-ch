import asyncio, os
from contextlib import chdir

from django.core.management.base import BaseCommand

from subprocess_monitor import SubprocessMonitor

from corpoch.chdedi.models import CHDediServer, GlobalConfig

class CHManager:
    def __init__(self, servers):
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        self._monitor = SubprocessMonitor(check_interval=10)
        self._servers = servers

    def __del__(self):
        for server in self._servers:
            server.pid = None
            server.save()

    async def run(self, server):
        with chdir(server.path):
            settings = server.write_settings()
            server.pid = await self._monitor.start_subprocess({ "cmd" : server.exec_str, "args" : [] })
            await server.asave()

    def restart(self):
        pass

    async def start(self):
        asyncio.create_task(self._monitor.run())
        for server in self._servers:
            print(f"Starting CH Server: {server}")
            await self.run(server)
        while True:
            await asyncio.sleep(1)



class Command(BaseCommand):
    help = 'Run Corpoch Dbot'

    def handle(self, *args, **options):
        print("Starting Clone Hero Dedicated Servers")
        mgr = CHManager(CHDediServer.objects.all())
        asyncio.run(mgr.start())
