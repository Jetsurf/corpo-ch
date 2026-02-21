import requests, tarfile, io, re, time
from django.core.management.base import BaseCommand
from corpoch.models import CHIcon, Chart
from corpoch.dbot.models import CHEmoji
from DiscordOauth2 import settings
import corpoch.dbot.tasks 

class Command(BaseCommand):
	help = 'Load CH Icons'
	
	def handle(self, *args, **options):
		response = requests.get('https://gitlab.com/api/v4/projects/25065576/repository/archive.tar.gz?path=public/icons')

		tar = tarfile.open(fileobj=io.BytesIO(response.content), mode='r:gz')
		members=tar.getmembers()
		for member in members:
			if member.name.lower().endswith('.png'):
				filename = re.sub(".*\\/(.*)png", "\\1png", member.name, flags=re.IGNORECASE)
				extracted_file = tar.extractfile(member)
				name = filename.replace(".png", "")
				print(f"Setting up icon {filename}")
				try:
					icon = CHIcon.objects.get(name=name)
					print(f"Icon exists in DB. ensuring dbot icon exists")
				except CHIcon.DoesNotExist:
					icon = None

				if not icon:
					print(f"Creating corpoch icon {name}")
					icon = CHIcon(name=name)
					icon.img.save(filename, extracted_file)
					icon.save()

				try:
					emoji = CHEmoji.objects.get(icon=icon)
				except CHEmoji.DoesNotExist:
					emoji = None

				if not emoji:
					print(f"Queueing bot task to create emoji {name} ")
					corpoch.dbot.tasks.add_bot_emoji(name)

				time.sleep(1)
