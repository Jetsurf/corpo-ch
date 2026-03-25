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

@app.task
def reload_cog(cog):
	print(f"Sending task to reload cog {cog}")
	reload_cog.apply_async(args=[cog])

@app.task
def send_qualifier_discord_dms(player, quali, req_subs, quali_end, guild, num_subs):
	print(f"Sending task to send DM to {player} for qualifier {quali} ({num_subs}/{req_subs})")
	send_qualifier_discord_dms.apply_async(args=[player.user, quali, req_subs, quali_end, guild, num_subs])

@app.task
def refresh_match_message(match_id):
	print(f"Sending task to refresh match {match_id}")
	refresh_match_message.apply_async(args=[match_id])

@app.task
def update_guild(guild_id):
	print(f"Updating information for guild {guild_id}")
	update_guild.apply_async(args=[guild_id])
