import os

from django.contrib import admin
from django_jsonform.widgets import JSONFormWidget

from django_pydantic_field import fields
from solo.admin import SingletonModelAdmin

from corpoch.chdedi.models import GlobalConfig, OpenConfig, TournamentConfig, CHDediServer

@admin.register(OpenConfig)
class OpenConfigAdmin(SingletonModelAdmin):
	formfield_overrides = { fields.PydanticSchemaField: {"widget": JSONFormWidget}, }

@admin.register(GlobalConfig)
class GlobalConfigAdmin(SingletonModelAdmin):
	formfield_overrides = { fields.PydanticSchemaField: {"widget": JSONFormWidget}, }
	readonly_fields = ['pid']
	exclude = ['to_restart', 'to_stop']

@admin.register(TournamentConfig)
class TournamentConfigAdmin(admin.ModelAdmin):
	model = TournamentConfig
	formfield_overrides = { fields.PydanticSchemaField: {"widget": JSONFormWidget}, }

@admin.register(CHDediServer)
class CHDediServerAdmin(admin.ModelAdmin):
	model = CHDediServer
	list_display = ('_ip', 'pid', '_name', 'config')
	readonly_fields = ['pid']
	formfield_overrides = { fields.PydanticSchemaField: {"widget": JSONFormWidget}, }
	actions = ['restart', 'stop']

	def _name(self, obj):
		return str(obj)

	def _ip(self, obj):
		return f"{obj.server_settings.ip}:{obj.server_settings.port}"

	@admin.action(description="(Re)start Server")
	def restart(modeladmin, request, queryset):
		for server in queryset:
			server.global_config.to_restart.add(server)
			server.save()

	@admin.action(description="Stop Server")
	def stop(modeladmin, request, queryset):
		for server in queryset:
			server.global_config.to_stop.add(server)
			server.save()
