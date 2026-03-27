from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class DiscordBackend(ModelBackend):
	def authenticate(self, request, user):
		UserModel = get_user_model()
		check_user = UserModel.objects.filter(id=user.id)

		if not check_user:
			new_user = UserModel.objects.create_new_discord_user(user)
			return new_user
		return check_user

	def get_user(self, user_id):
		UserModel = get_user_model()
		try:
			return UserModel.objects.get(id=user_id)
		except UserModel.DoesNotExist:
			return None
