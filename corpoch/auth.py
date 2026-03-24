from django.contrib.auth.backends import BaseBackend

from .models import DiscordUser

class DiscordBackend(BaseBackend):
	def authenticate(self, request, user):
		check_user = DiscordUser.objects.filter(id=user.id)
		if not check_user:
			new_user = DiscordUser.objects.create_new_discord_user(user)
			return new_user
		return check_user

	def get_user(self, id):
		try:
			return DiscordUser.objects.get(id=id)
		except DiscordUser.DoesNotExist:
			return None
