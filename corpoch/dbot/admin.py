from django.contrib import admin
from corpoch.dbot.models import Guilds, Channels, Roles
from django.utils.html import mark_safe

import corpoch.dbot.tasks

@admin.register(Guilds)
class GuildAdmin(admin.ModelAdmin):
	list_display = ('_icon', '_id', 'name')
	readonly_fields = ['name', 'icon', 'deleted']
	actions = ['update_discord_guild']

	def _id(self, obj):
		return str(obj.id)

	@mark_safe
	def _icon(self, obj):
		if obj.icon:
			return f'<img src="{obj.icon}" width="24" height="24"'
		else:
			return "None"

	@admin.action(description="Update Discord Info")
	def update_discord_guild(modeladmin, request, queryset):
		for guild in queryset:
			corpoch.dbot.tasks.update_guild(guild.id)

@admin.register(Channels)
class ChannelAdmin(admin.ModelAdmin):
	list_display = ('_id', 'guild', 'name')
	readonly_fields = ['name', 'deleted']

	def _id(self, obj):
		return str(obj.id)

@admin.register(Roles)
class RoleAdmin(admin.ModelAdmin):
	list_display = ('_id', 'guild', 'name')
	readonly_fields = ['name', 'deleted']

	def _id(self, obj):
		return str(obj.id)
