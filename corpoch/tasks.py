from celery import Celery, shared_task, Task
from celery.schedules import crontab
from django.db import close_old_connections, connection
from django.utils import timezone

from corpoch.models import TournamentPlayer, Qualifier, QualifierSubmission, Match, DiscordUser
from corpoch.dbot.models import Guilds
from corpoch.providers import GSheets
from corpoch.dbot import tasks

app = Celery()

@app.task
def upload_qualifiers_gsheet():
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
def upload_completed_match_gsheet():
	close_old_connections()
	matches = Match.objects.all().filter(finished=True).filter(submitted=False)
	sheet = GSheets()
	sheet.login()
	print(f"GSHEETS: Running gsheets upload for completed matches")
	for match in matches:
		if len(match.players.all()) > 0:
			print(f"GSHEETS: Uploading completed match {match.id} to tourney config sheet")
			sheet.set_submission(match)
			sheet.submit_completed()
			match.submitted = True
			match.save()
	close_old_connections()

@app.task
def send_qualifier_discord_dms():
	close_old_connections()
	for qualifier in Qualifier.objects.all().filter(required_submissions__gt=1, end_time__gt=timezone.now()):
		for ply in TournamentPlayer.objects.all().filter(tournament=qualifier.tournament):
			submissions = QualifierSubmission.objects.all().filter(player=ply)
			if len(submissions) < qualifier.required_submissions:
				tasks.send_qualifier_discord_dms(ply, str(qualifier), qualifier.required_submissions, qualifier.end_time, qualifier.tournament.guild, len(submissions))
	close_old_connections()

@app.task
def update_all_guilds():
	close_old_connections()
	for guild in Guilds.objects.all().filter(deleted=False):
		tasks.update_guild(guild.id)
	close_old_connections()

@app.task
def update_all_users():
	close_old_connections()
	for user in DiscordUser.objects.all():
		tasks.update_user(user.id)
	close_old_connections()

@app.task
def update_gsheet(submission_id, *args, **kwargs):
	close_old_connections()
	try:
		sub = Match.objects.get(id=submission_id)
	except Match.DoesNotExist:
		sub = None
	try:
		if not sub:
			sub = QualifierSubmission.objects.get(id=submission_id)
	except QualifierSubmission.DoesNotExist:
		print(f"Did not find qualifier submission or match ID for {submission_id}")
		return #Probably want to throw exception?

	sheet = GSheets()
	sheet.login()
	sheet.set_submission(sub)
	if isinstance(sub, Match):
		sheet.update_match()
	elif isinstance(sub, QualifierSubmission):
		sheet.update_qualifier()
	close_old_connections()
