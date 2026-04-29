import discord

async def get_chart_emoji(bot, chart):
	from corpoch.models import Chart
	from corpoch.dbot.models import CHEmoji
	try:
		emoji = await CHEmoji.objects.select_related().aget(icon_id=chart['icon'] if isinstance(chart, dict) else chart.icon)
	except CHEmoji.DoesNotExist:
		emoji = await CHEmoji.objects.select_related().aget(icon_id='ch_default_icon')
	return await bot.fetch_emoji(emoji.id)

def build_chart_str(steg) -> str:
	chartStr = f"Chart: {steg.artist_name} - {steg.song_name} ({steg.charter_name})" + (f" [{steg.playback_speed}%]" if steg.playback_speed != 100 else '') + "\n"
	chartStr += f"Run Time: <t:{int(steg.score_timestamp.timestamp())}:f>\n"
	chartStr += f"Game Version: {steg.game_version}"
	return chartStr

def build_stats_embed(steg, title: str) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = title
		embed.add_field(name="Submission Stats", value=build_chart_str(steg), inline=False)
		for i, player in enumerate(steg.players):
			plyStr = f"Score: {player.score}\n"
			plyStr += f"Notes Hit: {player.notes_hit}/{player.total_notes} - {(player.notes_hit/player.total_notes) * 100:.2f}% {' - 👑' if player.is_fc else f'(-{player.notes_missed})'}\n"
			plyStr += f"Overstrums: (+){player.excess_hits}\n"
			plyStr += f"Ghosts: {player.frets_ghosted}\n"
			plyStr += f"SP Phrases: {player.sp_phrases_earned}/{player.sp_phrases_total}\n"
			embed.add_field(name=f"Player: `{player.profile_name}`", value=plyStr, inline=False)
		embed.set_footer(text=f"Chart MD5: `{steg.checksum}`")#Get steg info to have chart icon key in output for footer.icon_url?
		return embed

def build_full_stats_embed(steg, title: str) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = title
		embed.add_field(name="Submission Stats", value=build_chart_str(steg), inline=False)
		for i, player in enumerate(steg.players):
			outStr = ""
			j = 1
			for attr in player.model_fields_set:
				if len(outStr) + (3 + len(attr) + len(str(getattr(player, attr)))) > 1024:
					embed.add_field(name=f"Player {player.profile_name} Raw Steg Info {j}", value=outStr, inline=False)
					j += 1
					outStr = ""
				outStr += f"{attr}: {getattr(player, attr)}\n"
			embed.add_field(name=f"Player {player.profile_name} Raw Steg Info {j}", value=outStr, inline=False)
		embed.set_footer(text=f"Chart md5 `{steg.checksum}`")
		return embed
