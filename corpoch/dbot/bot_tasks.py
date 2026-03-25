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
		squashed_name = sub("[^\\w]", "_", "".join(c for c in normalize('NFD', name) if category(c) != 'Mn'))
		try:
			emoji = await bot.create_emoji(name=squashed_name, image=f.read())
		except discord.errors.HTTPException:
			foundEmoji = False
			for tst in await bot.fetch_emojis():
				if tst.name == squashed_name:
					emoji = tst 
					foundEmoji = True
					break
			if not foundEmoji:
				print(f"Error on creating/finding emoji {name}")
				return
	new = CHEmoji(id=emoji.id, icon=dbIcon)
	await new.asave()

async def reload_cog(bot, cog):
	try:
		print(f"Reloading cog: {cog}")
		bot.unload_extension(cog)
		bot.load_extension(cog)
	except Exception as e:
		print(f"Reloading cog: {cog} failed: {e}")

async def send_qualifier_discord_dms(bot, player, quali, req_subs, quali_end, guild, num_subs):
	print(f"Sending reminder to {player} for {quali}")
	guild = bot.get_guild(guild)
	try:
		user = await guild.fetch_member(player)
	except:
		print(f"Can't find user {player} in guild {guild}")
		return
	if user.can_send():
		outStr = f"Hey! I wanted to quick remind you that the {quali} qualifier deadline is coming up at <t:{int(quali_end.timestamp())}:f>!\n"
		outStr += f"You've only submitted {num_subs} out of {req_subs} times, and need to submit before the deadline!"
		await user.send(outStr)
	else:
		print(f"Can't DM {player}")

async def refresh_match_message(bot, match_id):
	from corpoch.models import Match
	match = await Match.objects.select_related().aget(id=match_id)
	print(f"Refreshing match view {match.id}")
	from corpoch.dbot.cogs.tourneycmds import DiscordMatch
	view = DiscordMatch(bot, uuid=match.id)
	await view.init()
	await view.finishMatch(view.msg)

async def update_guild(bot, guild_id):
	print(f"Updating info for guild {guild_id}")
	guild = bot.get_guild(guild_id)
	from corpoch.dbot.models import Guilds
	dbguild = Guilds.objects.get(id=guild_id)

	if not guild:
		print(f"Guild {guild_id} is no longer visible - marking deleted")
		dbguild.deleted = True
		await dbguild.asave()
		return

	dbguild.name = guild.name
	if guild.icon:
		dbguild.icon = guild.icon.url

	for role in await guild.fetch_roles():
		from corpoch.dbot.models import Roles
		theRole, created = Roles.objects.get_or_create(id=role.id, guild=dbguild)
		theRole.name = role.name
		await theRole.asave()

	for channel in await guild.fetch_channels():
		from corpoch.dbot.models import Channels
		theChannel, created = Channels.objects.get_or_create(id=channel.id, guild=dbguild)
		theChannel.name = channel.name
		await theChannel.asave()

	await dbguild.asave()
