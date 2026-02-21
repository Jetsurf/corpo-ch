from django.db import models
from corpoch.models import CHIcon

class CHEmoji(models.Model):
	id = models.BigIntegerField(verbose_name="AppEmoji ID", db_index=True, primary_key=True)
	icon = models.ForeignKey(CHIcon, related_name="discord", verbose_name="Emote ID", null=False, blank=False, default=-1, on_delete=models.CASCADE)

	class Meta:
		verbose_name = "Chart Icon"
		verbose_name_plural = "Chart Icons"