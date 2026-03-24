from django.db import models
from datetime import datetime
from django.contrib.auth.models import BaseUserManager

class DiscordOAuth2Manager(BaseUserManager):
	def create_new_discord_user(self, user_data):
		new_user = self.get_or_create(username=user_data.global_name,
			id=user_data.id,
			global_name=user_data.global_name,
			avatar=user_data.avatar,
			public_flags=user_data.public_flags,
			flags=user_data.flags,
			locale=user_data.locale,
			mfa_enabled=user_data.mfa_enabled,
			last_login=datetime.now(),
		)
		new_user.set_unusuable_password()
		new_user.save()
		return new_user
