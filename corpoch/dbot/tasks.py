import logging

from discord import AppEmoji
from corpoch.celery import app

logger = logging.getLogger(__name__)

@app.task
def set_group_role(user_id, guild_id, role_id):
	print(f"Sending task corpoch.dbot.set_group_role({user_id}, {guild_id}, {role_id})")
	set_group_role.apply_async(args=[user_id, guild_id, role_id])

@app.task
def add_bot_emoji(name):
	print(f"Sending task corpoch.dbot.add_bot_emoji({name})")
	add_bot_emoji.apply_async(args=[name])
