import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DiscordOauth2.settings")

from django.apps import apps
from django.conf import settings

AUTHENTICATION_BACKENDS = [
    'auth.DiscordBackend', 
    'django.contrib.auth.backends.ModelBackend',
]

DEBUG = os.getenv("DEBUG")
BOT_TOKEN = os.getenv("BOT_TOKEN")

CELERY_BROKER_URL = settings.CELERY_BROKER_URL
CELERY_RESULT_BACKEND = settings.CELERY_RESULT_BACKEND

COGS_ENABLED = os.getenv("COGS_ENABLED").split(',')
HOME_GUILD_ID = os.getenv("HOME_GUILD_ID")

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
