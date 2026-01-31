import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'corpoch.settings')

app = Celery('corpoch')
app.autodiscover_tasks()