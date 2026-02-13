import os
from dotenv import load_dotenv
from pathlib import Path
from celery.schedules import crontab

load_dotenv('../')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DiscordOauth2.settings")

CELERY_BEAT_SCHEDULE = {
    'upload_qualifiers_gsheet': {
        'task': 'corpoch.upload_qualifiers_gsheet',
        'schedule': crontab(minute='*/2'),
    },
}
