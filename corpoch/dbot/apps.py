from django.apps import AppConfig
from . import __version__
from django.utils import autoreload
from corpoch.dbot import settings 
from corpoch.dbot.tasks import reload_cog

class DiscordBotConfig(AppConfig):
	name = 'corpoch.dbot'
	label = 'dbot'
	verbose_name = f'Corpo CH Discord Bot v{__version__}'
