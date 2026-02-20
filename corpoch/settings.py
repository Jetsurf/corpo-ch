import os
from dotenv import load_dotenv
from pathlib import Path
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DiscordOauth2.settings")

from django.conf import settings

CHOPT_PATH = os.getenv("CHOPT_PATH")
CHOPT_OUTPUT = os.getenv("CHOPT_OUTPUT")
CHSTEG_PATH = os.getenv("CHSTEG_PATH")
CHOPT_URL = os.getenv("CHOPT_URL")
