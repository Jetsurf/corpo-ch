import json

from django.contrib import admin
from corpoch.models import Chart, Tournament, TournamentConfig, TournamentBracket, TournamentQualifier, TournamentPlayer
from corpoch.models import TournamentMatchCompleted, TournamentMatchOngoing, BracketGroup, QualifierSubmission, CH_MODIFIERS

from corpoch.providers import EncoreClient

@admin.register(Chart)
class ChartAdmin(admin.ModelAdmin):
	list_display = ('name',  'charter', 'artist', 'album', 'speed', '_modifiers')
	actions = ['run_encore_import']

	def _modifiers(self, obj):
		return obj.modifiers

	def modifiers_long(self, obj):
		out = []
		for i in range(0, len(obj.modifiers)):
			out.append(CH_MODIFIERS[i][1])
		return out

	@admin.action(description="Run Encore import")
	def run_encore_import(modeladmin, request, queryset):
		encore = EncoreClient()
		for chart in queryset:
			if chart.blake3:
				print(f"Query = {chart.encore_blake3_query}")
				search = encore.search(chart.encore_blake3_query)
				print(f"search {search}")
			else:
				search = encore.search(chart.encore_search_query)

			if len(search) == 0:
				print(f"Chart {chart.name} encore lookup with query {chart.encore_search_query} failed with {search}")
				continue
			if len(search) > 1:
				print(f"Chart {chart.name} returned multiple results")
				continue

			newChart = search[0]
			print(f"new chart: {newChart}")
			chart.url = encore.url(newChart)
			chart.name = newChart['name']
			chart.blake3 = newChart['md5'] #Encore's md5 uses blake3
			chart.md5 = encore.get_md5(newChart)
			chart.album = newChart['album']
			chart.artist = newChart['artist']
			chart.charter = newChart['charter']
			chart.save()

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
	list_display = ('guild', 'active')

@admin.register(TournamentConfig)
class TournamentConfigAdmin(admin.ModelAdmin):
	list_display = ('tournament', 'ref_role', 'proof_channel', 'version')

@admin.register(TournamentBracket)
class TournamentBracketAdmin(admin.ModelAdmin):
	list_display = ("name", 'tournament')

@admin.register(TournamentPlayer)
class TournamentPlayerAdmin(admin.ModelAdmin):
	list_display = ('user', 'tournament', 'ch_name', 'is_active')

@admin.register(TournamentQualifier)
class TournamentQualifierAdmin(admin.ModelAdmin):
	list_display = ('id', 'tournament')

@admin.register(BracketGroup)
class BracketGroupAdmin(admin.ModelAdmin):
	list_display = ('tournament', 'bracket_name', 'name', 'group_players')

	def tournament(self, obj):
		return obj.bracket.tournament.name

	def group_players(self, obj):
		return ", ".join([player.ch_name for player in obj.players.all()])

	def bracket_name(self, obj):
		return obj.bracket.name

@admin.register(QualifierSubmission)
class QualifierSubmission(admin.ModelAdmin):
	list_display = ('quali', 'qualifier', 'player_ch_name')

	def player_ch_name(self, obj):
		return obj.player.ch_name

@admin.register(TournamentMatchCompleted)
class TournamentMatchCompletedAdmin(admin.ModelAdmin):
	list_display = ('__str__', 'processed', 'bracket_name', 'group', 'player1_ch_name', 'player2_ch_name', 'started_on', 'version')

	def bracket_name(self, obj):
		return obj.group.bracket.name

	def player1_ch_name(self, obj):
		return obj.player1.ch_name

	def player2_ch_name(self, obj):
		return obj.player2.ch_name

	def version(self, obj):
		return obj.group.bracket.tournament.config.version

@admin.register(TournamentMatchOngoing)
class TournamentMatchOngoingAdmin(admin.ModelAdmin):
	list_display = ('__str__', 'processed', 'bracket_name', 'group', 'player1_ch_name', 'player2_ch_name', 'started_on', 'version')

	def bracket_name(self, obj):
		return obj.group.bracket.name

	def player1_ch_name(self, obj):
		return obj.player1.ch_name

	def player2_ch_name(self, obj):
		return obj.player2.ch_name
