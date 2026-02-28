from celery import Celery, shared_task, Task
from celery.schedules import crontab
from django.db import close_old_connections, connection

from corpoch.models import TournamentPlayer, QualifierSubmission, TournamentMatchOngoing, TournamentMatchCompleted
from corpoch.providers import GSheets

app = Celery()

class ConnectionRefreshingTask(Task):
	abstract = True
 
	def before_start(self, task_id, args, kwargs):
		self.refresh_connection()
		super().before_start(task_id, args, kwargs)
 
	def refresh_connection(self):
		if not connection.is_usable():
			connection.close()

@app.task
def upload_qualifiers_gsheet(base=ConnectionRefreshingTask):
	close_old_connections()
	qualis = QualifierSubmission.objects.all().filter(submitted=False)
	sheet = GSheets()
	sheet.login()
	print(f"GSHEETS: Running gsheets upload for unsubmitted qualifiers")
	for quali in qualis:
		print(f"GSHEETS: Uploading ({quali}) to sheet")
		sheet.set_submission(quali)
		sheet.submit_qualifier()
	close_old_connections()

@app.task
def upload_completed_match_gsheet(base=ConnectionRefreshingTask):
	close_old_connections()
	matches = TournamentMatchCompleted.objects.all().filter(processed=False)
	sheet = GSheets()
	sheet.login()
	print(f"GSHEETS: Running gsheets upload for completed matches")
	for match in matches:
		print(f"GSHEETS: Uploading completed match {match.id} to tourney config sheet")
		sheet.set_submission(match)
		sheet.submit_completed()
		match.processed = True
		match.save()
	close_old_connections()
