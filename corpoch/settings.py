import os
from dotenv import load_dotenv
from pathlib import Path
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DiscordOauth2.settings")

from django.conf import settings

BASE_URL = os.getenv("BASE_URL")
MEDIA_ROOT = os.getenv("MEDIA_ROOT")
MEDIA_URL = os.getenv("MEDIA_URL")

CHOPT_PATH = os.getenv("CHOPT_PATH")
CHOPT_OUTPUT = os.getenv("CHOPT_OUTPUT")
CHSTEG_PATH = os.getenv("CHSTEG_PATH")
CHOPT_URL = os.getenv("CHOPT_URL")

SALT_KEY = os.getenv("DB_CRYPT_KEY")

DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800 #50 MB
