from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from django_pydantic_field import SchemaField
from solo.models import SingletonModel
from corpoch.chdedi.types import CHServerSettings, CHServerSpecificSettings, CHRedisSettings, SERVER_CONFIG_CHOICES

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
	pid = models.PositiveIntegerField(verbose_name="Process PID")
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
			conf = OpenConfig.objects.get()
		elif self.config == "tournament":
			conf = tournament_config
		else:
			return None

		return CHSettings(conf | self.serverSettings)
