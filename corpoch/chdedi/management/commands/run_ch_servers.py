from django.core.management.base import BaseCommand

from subprocess_monitor import SubprocessMonitor

from corpoch.chdedi.models import CHDediServer

class CHManager:
    def __init__(self, server: CHDediServer):
        self._monitor = SubprocessMonitor(host=server.settings.ip, port=server.settings.port)

class Command(BaseCommand):
    help = 'Run Corpoch Dbot'

    def handle(self, *args, **options):
        launcher.run_bot()
