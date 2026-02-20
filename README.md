# Corpo CH
The Corpo CH Django App/Discord Bot

Clone Hero Tournament organizer and tools.

## Installation

Git clone this repo down to a new folder.

Create Discord bot app -> needs discord.intents.members = True

Install redis+MySQL + populate .env vars for needed fields.

Install requirements `pip3 install -r requirements.txt`

Make migrations -> `python3 manage.py makemigrations corpoch`

Migrate -> `python3 manage.py migrate`

Collect Static `python3 manage.py collectstatic`

Start Processes:
 - `celery -A corpoch beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler`
 - `celery -A corpoch worker -l info`
 - `python3 manage.py runserver`
 - `python3 manage.py run_dbot`

