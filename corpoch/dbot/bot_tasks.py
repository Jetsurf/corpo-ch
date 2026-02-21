import importlib
import io
import logging
import warnings
import discord
from datetime import timedelta
from unicodedata import normalize, category
from re import sub

from discord import Embed, File, AppEmoji
from discord.ext import tasks
from discord.ext.commands import Bot

import django
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

@tasks.loop()
async def run_tasks(bot: Bot):
	django.db.close_old_connections()
	if len(bot.tasks) > 0:
		task, args, kwargs = bot.tasks.pop(0)
		try:
			await task(bot, *args, **kwargs)
			bot.dispatch("dbot_task_completed", task.__name__)
		except Exception as e:
			bot.dispatch("dbot_task_failed", task.__name__, args, kwargs, e)
			print(f"Failed to run task {task} {args} {kwargs} {e}")
	else:
		run_tasks.stop()
	django.db.close_old_connections()

async def set_group_role(bot, user_id, guild_id, role_id):
	print(f"Setting Group role {role_id} discord ID {user_id}")

	guild = bot.get_guild(guild_id)
	user = await guild.fetch_member(user_id)
	role = await guild.fetch_role(role_id)
	await user.add_roles(role)

async def add_bot_emoji(bot, name):
	from corpoch.dbot.models import CHEmoji
	from corpoch.models import CHIcon
	dbIcon = await CHIcon.objects.aget(name=name)
	with open(dbIcon.img.path, "rb") as f:
		if len(name) < 2:
			name += "_"
		try:
			squashed_name = sub("[^\\w]", "_", "".join(c for c in normalize('NFD', name) if category(c) != 'Mn'))
			emoji = await bot.create_emoji(name=squashed_name, image=f.read())
		except discord.errors.HTTPException:
			print(f"Icon {name} has a dupe?")
			return
	new = CHEmoji(id=emoji.id, icon=dbIcon)
	await new.asave()
