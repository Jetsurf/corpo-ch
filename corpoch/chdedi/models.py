from contextlib import chdir

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from django_pydantic_field import SchemaField
from solo.models import SingletonModel
from corpoch.chdedi.types import CHServerSettings, CHServerSpecificSettings, CHRedisSettings, SERVER_CONFIG_CHOICES, CHSettings, CHOnlineSettings

class GlobalConfig(SingletonModel):
	redis = SchemaField(CHRedisSettings, verbose_name="Redis Config", null=True, blank=True)

	class Meta:
		verbose_name = "Global Settings"
		verbose_name_plural = "Global Settings"

class OpenConfig(SingletonModel):
	settings = SchemaField(CHServerSettings, verbose_name="Open Server Config", null=True, blank=True)

	class Meta:
		verbose_name = "Server Open Settings"
		verbose_name_plural = "Server Open Settings"

class TournamentConfig(models.Model):
	tournament = models.ForeignKey("corpoch.Tournament", verbose_name="Settings for Tournament", on_delete=models.CASCADE, null=True, blank=True)
	settings = SchemaField(CHServerSettings, verbose_name="Dedicated Server Config", null=True, blank=True)

	class Meta:
		verbose_name = "Server Tournament Settings"
		verbose_name_plural = "Server Tournament Settings"

class CHDediServer(models.Model):
	id = models.AutoField(primary_key=True)
	pid = models.PositiveIntegerField(verbose_name="Process PID", null=True, blank=True)
	path = models.CharField(verbose_name="Server Path", max_length=40, default="~/CHDediServer")
	config = models.CharField(verbose_name="Config Option", choices=SERVER_CONFIG_CHOICES, max_length=16, default=SERVER_CONFIG_CHOICES[0])
	tournament_config = models.ForeignKey(TournamentConfig, verbose_name="Tournament Configuration", on_delete=models.SET_NULL, null=True, blank=True)
	server_settings = SchemaField(CHServerSpecificSettings, verbose_name="Configuration", null=True, blank=True)

	class Meta:
		verbose_name = "Servers"
		verbose_name_plural = "Servers"

	@property
	def settings(self):
		if self.config == "open":
			conf = OpenConfig.objects.get().settings
		elif self.config == "tournament":
			conf = self.tournament_config.settings
		else:
			return None

		redis = GlobalConfig.objects.get().redis
		online = CHOnlineSettings.model_validate(self.server_settings.model_dump() | conf.model_dump())
		return CHSettings.model_validate({ 'redis' : redis, 'online' : online })

	def __str__(self):
		return self.server_settings.name

	def write_settings(self):
		fileStr = ""
		for section, val1 in iter(self.settings):
			fileStr += f"[{section}]\n"
			for opt, val2 in iter(val1):
				fileStr += f"{opt} = {val2}\n"
			fileStr += "\n"
		with chdir(self.path):
			with open("settings.ini", "w") as f:
				f.write(fileStr)

