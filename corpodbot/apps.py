from django.apps import AppConfig

from . import __version__

class CorpoDiscordBotConfig(AppConfig):
    name = 'corpodbot'
    label = 'corpodbot'
    verbose_name = f'Corpo Discord Bot v{__version__}'