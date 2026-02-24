from django.dispatch import receiver
from django.utils.autoreload import autoreload_started, BaseReloader, file_changed
from corpoch.dbot.tasks import reload_cog
from corpoch.dbot import settings

@receiver(autoreload_started)
def register_watches(sender: BaseReloader, **kwargs):
	print("Registering cogs auto-watch")
	sender.watch_dir(settings.BASE_DIR, "**/corpoch/dbot/cogs/*.py")

@receiver(file_changed)
def process_file_changed(file_path: str, **kwargs):
	if file_path.suffix in [settings.COGS_ENABLED]:
		# Just log debug information for now
		cog = file_path.replace('*corpoch/dbot/cogs/', '')
		cog = cog.replace('.py', '')
		print(f"Processing file {cog}")
		reload_cog(cog)
	return True
