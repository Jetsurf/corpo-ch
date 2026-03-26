from corpoch.models import Chart
from corpoch.dbot.models import CHEmoji

async def get_chart_emoji(bot, chart):
	try:
		emoji = await CHEmoji.objects.select_related().aget(icon_id=chart['icon'] if isinstance(chart, dict) else chart.icon)
	except CHEmoji.DoesNotExist:
		emoji = await CHEmoji.objects.select_related().aget(icon_id='ch_default_icon')
	return await bot.fetch_emoji(emoji.id)
