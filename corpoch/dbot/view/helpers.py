from corpoch.models import Chart
from corpoch.dbot.models import CHEmoji
from asgiref.sync import sync_to_async

async def get_chart_emoji(bot, chart):
	if isinstance(chart, Chart):
		icon = await sync_to_async(lambda: chart.icon)()
	try:
		icon = await CHEmoji.objects.select_related().aget(icon_id=chart['icon'] if isinstance(chart, dict) else icon)
	except CHEmoji.DoesNotExist:
		icon = await CHEmoji.objects.select_related().aget(icon_id='ch_default_icon')
	return await bot.fetch_emoji(icon.id)