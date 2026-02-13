from celery import Celery, shared_task
from celery.schedules import crontab

from corpoch.models import TournamentPlayer, QualifierSubmission, TournamentMatchOngoing, TournamentMatchCompleted
from corpoch.providers import GSheets
app = Celery()

@app.task
def upload_qualifiers_gsheet():
	qualis = QualifierSubmission.objects.all().filter(submitted=False)
	print(f"Running gsheets upload")
	for quali in qualis:
		sheet = GSheets(quali)
		sheet.init()
		sheet.submit_qualifier()
