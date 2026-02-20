import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DiscordOauth2.settings")

from django.apps import apps
from django.conf import settings

BOT_TOKEN = os.getenv("BOT_TOKEN")

CELERY_BROKER_URL = settings.CELERY_BROKER_URL
CELERY_RESULT_BACKEND = settings.CELERY_RESULT_BACKEND

HOME_GUILD_ID = os.getenv("HOME_GUILD_ID")
