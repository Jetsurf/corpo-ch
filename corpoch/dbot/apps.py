from django.apps import AppConfig

from . import __version__

class DiscordBotConfig(AppConfig):
    name = 'corpoch.dbot'
    label = 'dbot'
    verbose_name = f'Corpo CH Discord Bot v{__version__}'
