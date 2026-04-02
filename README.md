# Corpo CH
The Corpo CH Django App/Discord Bot

Clone Hero Tournament organizer and tools.

## Installation

Git clone this repo down to a new folder.

Create Discord bot app -> needs discord.intents.members = True

Install redis+MySQL + populate .env vars for needed fields.

Install requirements `pip3 install -r requirements.txt`

Migrate -> `python3 manage.py migrate`

Collect Static -> `python3 manage.py collectstatic`

Load CH Icons/AppEmotes -> `python3 manage.py ch_icon_import`

Login to Main Site to create a discord user.

Set your user as superuser. `python3 manage.py set_discord_superuser -d DISCORDID`

(Optional) Create Google Service Account API. Upload contents of json file into admin UI

Start Processes:
 - `celery -A corpoch beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler`
 - `celery -A corpoch worker -l info`
 - `python3 manage.py runserver`
 - `python3 manage.py run_dbot`

Needs nginx/apache2/web server hosting the static directories - preferable turn off autoindexing/view on images/qualifiers

Setup periodic tasks for management in admin UI:
 - corpoch.tasks.update_all_users - 6 hours
 - corpoch.tasks.update_all_guilds - 20 mins
 - corpoch.tasks.upload_qualifiers_gsheet - 5 mins
 - corpoch.tasks.upload_completed_match_gsheet - 5 mins

More to come!

## Credits
 - All Contributors
 - The CH Competitive Scene
 - [CHOpt](https://github.com/GenericMadScientist/CHOpt) [CH Steg Reader](https://github.com/GenericMadScientist/CH-Steg-Reader) - [@GenericMadScientist](https://github.com/GenericMadScientist)
 - [Hydra](https://github.com/DragonDelgar/hydra) - [@DragonDelgar](https://github.com/DragonDelgar)
