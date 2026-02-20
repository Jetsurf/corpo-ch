from celery import Celery, shared_task
from celery.schedules import crontab

from corpoch.models import TournamentPlayer, QualifierSubmission, TournamentMatchOngoing, TournamentMatchCompleted
from corpoch.providers import GSheets
app = Celery()

@app.task
def upload_qualifiers_gsheet():
	qualis = QualifierSubmission.objects.all().filter(submitted=False)
	sheet = GSheets()
	sheet.login()
	print(f"GSHEETS: Running gsheets upload for unsubmitted qualifiers")
	for quali in qualis:
		print(f"GSHEETS: Uploading ({quali}) to sheet")
		sheet.set_submission(quali)
		sheet.submit_qualifier()
