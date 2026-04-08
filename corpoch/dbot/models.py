from django.db import models

class CHEmoji(models.Model):
	"""
	Represents a Discord Emoji used with a Chart Icon.
	"""
	id = models.BigIntegerField(verbose_name="AppEmoji ID", db_index=True, primary_key=True, help_text="Discord snowflake ID of the AppEmoji.")
	icon = models.ForeignKey('corpoch.CHIcon', related_name="discord", verbose_name="Emote ID", null=False, blank=False, default=-1, on_delete=models.CASCADE, help_text="Associated CHIcon.")

	class Meta:
		verbose_name = "Chart Icon"
		verbose_name_plural = "Chart Icons"

class Guilds(models.Model):
	"""
	Represents a Discord Guild a Tournament is ran in.
	"""
	id = models.BigIntegerField(primary_key=True, help_text="Discord snowflake ID for a Guild.")
	name = models.CharField(max_length=100, null=True, blank=True, help_text="Name of a Discord Guild.")
	icon = models.CharField(max_length=255, null=True, blank=True, help_text="The avatar for a Guild.")
	deleted = models.BooleanField(default=False, help_text="Is deleted/not visible by bot.")

	class Meta:
		verbose_name = 'Guild'
		verbose_name_plural = 'Guilds'

	def __str__(self):
		return str(self.name)

class Channels(models.Model):
	"""
	Represents a channel in a Discord Guild for a Tournament. 
	"""
	id = models.BigIntegerField(primary_key=True, help_text="Discord snowflake ID of a channel.")
	guild = models.ForeignKey(Guilds, on_delete=models.CASCADE, help_text="Guild this channel is in.")
	name = models.CharField(max_length=100, null=True, blank=True, help_text="Name of a discord channel.")
	deleted = models.BooleanField(default=False, help_text="Is deleted/not visible by bot.")

	def __str__(self):
		return f'#{self.name}'

	class Meta:
		verbose_name = 'Channel'
		verbose_name_plural = 'Channels'

class Roles(models.Model):
	"""
	Represents a role in a Discord Guild for a Tournament. 
	"""
	id = models.BigIntegerField(primary_key=True, help_text="Discord snowflake ID of a role.")
	guild = models.ForeignKey(Guilds, on_delete=models.CASCADE, help_text="Guild this channel is in.")
	name = models.CharField(max_length=100, null=True, blank=True, help_text="Name of a discord role.")
	deleted = models.BooleanField(default=False, help_text="Is deleted/not visible by bot.")

	class Meta:
		verbose_name = 'Role'
		verbose_name_plural = 'Roles'

	def __str__(self):
		return str(self.name)
