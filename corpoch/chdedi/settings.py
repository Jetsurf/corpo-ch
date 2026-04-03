import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DiscordOauth2.settings")

from django.apps import apps
from django.conf import settings

BASE_URL = os.getenv("BASE_URL")