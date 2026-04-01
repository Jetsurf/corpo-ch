from django.db import models

class CHEmoji(models.Model):
	id = models.BigIntegerField(verbose_name="AppEmoji ID", db_index=True, primary_key=True)
	icon = models.ForeignKey('corpoch.CHIcon', related_name="discord", verbose_name="Emote ID", null=False, blank=False, default=-1, on_delete=models.CASCADE)

	class Meta:
		verbose_name = "Chart Icon"
		verbose_name_plural = "Chart Icons"

class Guilds(models.Model):
	id = models.BigIntegerField(primary_key=True)
	name = models.CharField(max_length=100, null=True, blank=True)
	icon = models.CharField(max_length=255, null=True, blank=True)
	deleted = models.BooleanField(default=False)

	class Meta:
		verbose_name = 'Guild'
		verbose_name_plural = 'Guilds'

	def __str__(self):
		return str(self.name)

class Channels(models.Model):
	id = models.BigIntegerField(primary_key=True)
	guild = models.ForeignKey(Guilds, on_delete=models.CASCADE)
	name = models.CharField(max_length=100, null=True, blank=True)
	deleted = models.BooleanField(default=False)

	def __str__(self):
		return f'#{self.name}'

	class Meta:
		verbose_name = 'Channel'
		verbose_name_plural = 'Channels'

class Roles(models.Model):
	id = models.BigIntegerField(primary_key=True)
	guild = models.ForeignKey(Guilds, on_delete=models.CASCADE)
	name = models.CharField(max_length=100, null=True, blank=True)
	deleted = models.BooleanField(default=False)

	class Meta:
		verbose_name = 'Role'
		verbose_name_plural = 'Roles'

	def __str__(self):
		return str(self.name)
