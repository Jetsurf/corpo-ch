from django.core.management.base import BaseCommand

from corpoch.dbot import launcher


class Command(BaseCommand):
    help = 'Run Corpoch Dbot'

    def handle(self, *args, **options):
        launcher.run_bot()