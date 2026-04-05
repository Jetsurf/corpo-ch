from datetime import datetime

from django.contrib.auth.models import BaseUserManager
from django.db import models

class DiscordOAuth2Manager(BaseUserManager):
	def create_new_discord_user(self, user_data):
		print(f"USER: {user_data}")
		new_user, created = self.get_or_create(id=user_data.id,
			global_name=user_data.globalname if user_data.global_name else user_data.display_name,
			avatar=user_data.avatar,
			public_flags=user_data.public_flags,
			flags=user_data.flags,
			locale=user_data.locale,
			mfa_enabled=user_data.mfa_enabled,
			last_login=datetime.now(),
		)
		new_user.save()
		return new_user
