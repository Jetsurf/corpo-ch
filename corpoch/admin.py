import json, time

from adminsortable2.admin import CustomInlineFormSet, SortableAdminBase, SortableStackedInline, SortableAdminMixin

from django_pydantic_field import fields
from django.contrib import admin
from django_jsonform.widgets import JSONFormWidget
from django.contrib.contenttypes.models import ContentType
from corpoch.models import Chart, Tournament, TournamentConfig, BracketRules, TournamentBracket, Qualifier, TournamentPlayer, GroupSeed, MatchRound, CHIcon
from corpoch.models import TournamentMatchCompleted, TournamentMatchOngoing, BracketGroup, QualifierSubmission, CH_MODIFIERS, MatchBan, GSheetAPI
from corpoch.providers import EncoreClient, GSheets
from django.utils.html import mark_safe
import corpoch.dbot.tasks

@admin.register(GSheetAPI)
class GSheetAPIAdmin(admin.ModelAdmin):
	pass

@admin.register(Chart)
class ChartAdmin(admin.ModelAdmin):
	list_display = ('_icon','name',  '_bracket', 'charter', 'artist', 'album', 'speed', '_modifiers', 'tiebreaker')
	list_filter = ['brackets', 'charter', 'artist', 'tiebreaker']
	readonly_fields = ['_icon']
	actions = ['run_encore_import']

	def _bracket(self,obj):
		retList = []
		for bracket in obj.brackets.iterator():
			retList.append(bracket)
		return retList

	def _modifiers(self, obj):
		return obj.modifiers

	def modifiers_long(self, obj):
		out = []
		for i in range(0, len(obj.modifiers)):
			out.append(CH_MODIFIERS[i][1])
		return out

	@mark_safe
	def _icon(self, obj):
		return f'<img src="{obj.icon.img.url}" width="24" height="24"'

	@admin.action(description="Run Encore import")
	def run_encore_import(modeladmin, request, queryset):
		encore = EncoreClient()
		for chart in queryset:
			search = encore.search(chart.encore_search_query)

			if len(search) == 0:
				print(f"Chart {chart.name} encore lookup with query {chart.encore_search_query} failed with {search}")
				continue
			if len(search) > 1:
				print(f"Chart {chart.name} returned multiple results")

			newChart = search[0]
			try:
				icon = CHIcon.objects.get(name=newChart['icon'])
			except CHIcon.DoesNotExist:
				icon = CHIcon.objects.get(name="ch_default_icon")

			chart.url = encore.url(newChart)
			chart.name = newChart['name']
			chart.icon = icon
			chart.blake3 = newChart['md5'] #Encore's md5 uses blake3
			chart.md5 = encore.get_md5_from_chart(newChart)
			chart.album = newChart['album']
			chart.artist = newChart['artist']
			chart.charter = newChart['charter']
			chart.save()

class TournamentConfigInline(admin.TabularInline):
	model = TournamentConfig
	extra = 0

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
	list_display = ('name', 'guild', 'active')
	inlines = [TournamentConfigInline]

class BracketRulesInline(admin.TabularInline):
	model = BracketRules
	extra = 0

@admin.register(TournamentBracket)
class TournamentBracketAdmin(admin.ModelAdmin):
	list_display = ("_name", 'tournament')
	list_filter = ['tournament']
	inlines = [BracketRulesInline]

	def _name(self, obj):
		return f"{obj}"

@admin.register(TournamentPlayer)
class TournamentPlayerAdmin(admin.ModelAdmin):
	list_display = ('user', 'tournament', 'ch_name', 'is_active')
	list_filter = ['tournament']

@admin.register(Qualifier)
class TournamentQualifierAdmin(admin.ModelAdmin):
	list_display = ('id', 'tournament')
	list_filter = ['tournament']

class SeedingInline(SortableStackedInline):
	model = GroupSeed
	extra = 1

@admin.register(BracketGroup)
class BracketGroupAdmin(SortableAdminBase, admin.ModelAdmin):
	list_display = ('name', 'tournament', 'bracket_name')#, 'group_players')
	inlines = [SeedingInline]
	list_per_page = 32
	actions = ['set_group_role']

	def tournament(self, obj):
		return obj.bracket.tournament.short_name

	def group_players(self, obj):
		return ", ".join([seed.player.ch_name for seed in obj.seeding.all()])

	def bracket_name(self, obj):
		return obj.bracket.name

	def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
		if db_field.name == "group_players":
			kwargs["queryset"] = Tournament.players.objects.all()
		return super(BracketGroupAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

	@admin.action(description="Set group role for players")
	def set_group_role(modeladmin, request, queryset):
		for group in queryset:
			tourney = group.bracket.tournament
			role = group.role
			guild = tourney.guild
			for seed in group.seeding.all():
				ply = seed.player.user
				corpoch.dbot.tasks.set_group_role(ply, guild, role)	

@admin.register(QualifierSubmission)
class QualifierSubmission(admin.ModelAdmin):
	formfield_overrides = { fields.PydanticSchemaField: {"widget": JSONFormWidget}, }
	list_display = ('id', 'qualifier', 'player_ch_name', '_score', '_miss', '_hit', '_excess', '_ghosts', '_phrases', 'submitted')
	list_filter = ["qualifier", "player"]
	actions = ['set_unsubmitted',"reread_steg", "resubmit_gsheet"]

	def tournament(self, obj):
		return obj.qualifier.tournament.short_name

	def player_ch_name(self, obj):
		return obj.player.ch_name

	def _score(self, obj):
		return obj.steg.players[0].score if len(obj.steg.players) > 0 else '-'

	def _miss(self, obj):
		return obj.steg.players[0].notes_missed if len(obj.steg.players) > 0 else '-'

	def _hit(self, obj):
		return obj.steg.players[0].notes_hit if len(obj.steg.players) > 0 else '-'

	def _excess(self, obj):
		return obj.steg.players[0].excess_hits if len(obj.steg.players) > 0 else '-'

	def _ghosts(self, obj):
		return obj.steg.players[0].frets_ghosted if len(obj.steg.players) > 0 else '-'

	def _phrases(self, obj):
		return obj.steg.players[0].sp_phrases_earned if len(obj.steg.players) > 0 else '-'

	@admin.action(description="Mark Qualifiers GSheet Unsent")
	def set_unsubmitted(modeladmin, request, queryset):
		for quali in queryset:
			quali.submitted = False
			quali.save()

	@admin.action(description="Reread steg data")
	def reread_steg(modeladmin, request, queryset):
		for quali in queryset:
			quali.steg = None
			quali.save()

	@admin.action(description="Correct GSheet Values")
	def resubmit_gsheet(modeladmin, request, queryset):
		sheet = GSheets()
		sheet.login()
		for quali in queryset:
			sheet.set_submission(quali)
			sheet.update_qualifier()
			time.sleep(1.5)

class RoundsOngoingInline(SortableStackedInline):
	model = MatchRound
	formfield_overrides = { fields.PydanticSchemaField: {"widget": JSONFormWidget}, }
	exclude = ['completed_match']
	extra = 1

class RoundsCompletedInline(SortableStackedInline):
	model = MatchRound
	exclude = ['ongoing_match']
	formfield_overrides = { fields.PydanticSchemaField: {"widget": JSONFormWidget}, }
	extra = 0

class BansOngoingInline(SortableStackedInline):
	model = MatchBan
	exclude = ['completed_match']
	extra = 1

class BansCompletedInline(SortableStackedInline):
	model = MatchBan
	exclude = ['ongoing_match']
	extra = 0

#TODO - Add match score to table
@admin.register(TournamentMatchCompleted)
class TournamentMatchCompletedAdmin(SortableAdminBase, admin.ModelAdmin):
	list_display = ('__str__', 'processed', 'bracket_name', 'group', '_match_players', 'started_on', 'version')
	inlines = [BansCompletedInline, RoundsCompletedInline]
	list_per_page = 16
	exclude = ['ongoing_match']
	actions = ['set_unsubmitted',"reread_steg", "resubmit_gsheet"]

	def bracket_name(self, obj):
		return obj.group.bracket.name

	def _match_players(self, obj):
		retList = []
		for seed in obj.match_players.iterator():
			retList.append(seed.player.ch_name)
		return retList

	def version(self, obj):
		return obj.group.bracket.tournament.config.version

	@admin.action(description="Mark Match GSheet Unsent")
	def set_unsubmitted(modeladmin, request, queryset):
		for match in queryset:
			match.submitted = False
			match.save()

	@admin.action(description="Reread steg data")
	def reread_steg(modeladmin, request, queryset):
		for match in queryset:
			for rnd in match.rounds:
				rnd.steg = None
				rnd.save()

	@admin.action(description="Correct GSheet Values")
	def resubmit_gsheet(modeladmin, request, queryset):
		sheet = GSheets()
		sheet.login()
		for quali in queryset:
			sheet.set_submission(quali)
			sheet.update_match()
			time.sleep(1.5)

@admin.register(TournamentMatchOngoing)
class TournamentMatchOngoingAdmin(SortableAdminBase, admin.ModelAdmin):
	list_display = ('__str__', 'processed', '_bracket_name', 'group', '_match_players', '_match_bans', 'started_on', 'version')
	inlines = [BansOngoingInline, RoundsOngoingInline]
	list_per_page = 16
	exclude = ['completed_match']

	def _bracket_name(self, obj):
		return obj.group.bracket.name

	def _match_players(self, obj):
		retList = []
		for seed in obj.match_players.iterator():
			retList.append(seed.player.ch_name)
		return retList

	def _match_bans(self, obj):
		retList = []
		for ban in MatchBan.objects.all().iterator():
			retList.append(ban.chart)
		return retList
