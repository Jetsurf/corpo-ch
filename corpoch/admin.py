import json, time

from adminsortable2.admin import CustomInlineFormSet, SortableAdminBase, SortableStackedInline, SortableAdminMixin

from django_pydantic_field import fields
from django.contrib import admin
from django_jsonform.widgets import JSONFormWidget
from django.contrib.contenttypes.models import ContentType
from corpoch.models import Chart, Tournament, TournamentConfig, BracketRules, Bracket, Qualifier, TournamentPlayer, GroupSeed, MatchRound, CHIcon
from corpoch.models import Match, Group, QualifierSubmission, CH_MODIFIERS, MatchBan, GSheetAPI
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
	actions = ['run_encore_import', 'import_song_ini']

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

	@admin.action(description="Import data from song.ini")
	def import_song_ini(modeladmin, request, queryset):
		from corpoch.providers import SNGHandler
		for chart in queryset:
			song = SNGHandler(chart.sngfile.open(mode='rb').read())
			songini = song.songini_model
			chart.name = songini.name
			chart.artist = songini.artist
			chart.album = songini.album
			chart.genre = songini.genre
			chart.charter = songini.charter
			chart.md5 = song.md5
			try:
				chart.icon = CHIcon.objects.get(name=songini.icon)
			except CHIcon.DoesNotExist:
				chart.icon = CHIcon.objects.get(name="ch_default_icon")
			chart.save()

class TournamentConfigInline(admin.TabularInline):
	model = TournamentConfig
	extra = 0

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
	list_display = ('name', 'guild', 'active')
	inlines = [TournamentConfigInline]
	actions = ['set_tournament_role', 'set_players_active']

	@admin.action(description="Set tournament role for players")
	def set_tournament_role(modeladmin, request, queryset):
		for tourney in queryset:
			role = tourney.role
			guild = tourney.guild
			for bracket in tourney.brackets.all():
				for group in bracket.groups.all():
					for seed in group.seeding.all():
						ply = seed.player.user
						corpoch.dbot.tasks.set_group_role(ply, guild, role)

	@admin.action(description="Set players as active")
	def set_players_active(modeladmin, request, queryset):
		for tourney in queryset:
			role = tourney.role
			guild = tourney.guild
			for bracket in tourney.brackets.all():
				for group in bracket.groups.all():
					for seed in group.seeding.all():
						seed.player.is_active = True
						seed.player.save()

class BracketRulesInline(admin.TabularInline):
	model = BracketRules
	extra = 0

@admin.register(Bracket)
class BracketAdmin(admin.ModelAdmin):
	list_display = ("_name", 'tournament')
	list_filter = ['tournament']
	inlines = [BracketRulesInline]
	actions = ['set_bracket_role']

	def _name(self, obj):
		return f"{obj}"

	@admin.action(description="Set bracket role for players")
	def set_bracket_role(modeladmin, request, queryset):
		for bracket in queryset:
			tourney = bracket.tournament
			role = bracket.role
			guild = tourney.guild
			for group in bracket.groups.all():
				for seed in group.seeding.all():
					ply = seed.player.user
					corpoch.dbot.tasks.set_group_role(ply, guild, role)

@admin.register(TournamentPlayer)
class TournamentPlayerAdmin(admin.ModelAdmin):
	list_display = ('user', 'tournament', 'ch_name', 'is_active')
	list_filter = ['tournament']
	actions = ["set_tournament_roles"]

	@admin.action(description="Set tournament roles")
	def set_tournament_roles(modeladmin, request, queryset):
		for ply in queryset:
			tourney = ply.tournament
			for seed in ply.group_seeding.all():
				grole = seed.group.role
				brole = seed.group.bracket.role
				trole = tourney.role
				print(f"Setting group roles for {ply.ch_name} {grole} - {brole} = {trole}")
				if grole is not None:
					corpoch.dbot.tasks.set_group_role(ply.user, ply.tournament.guild, grole)
				if brole is not None:
					corpoch.dbot.tasks.set_group_role(ply.user, ply.tournament.guild, brole)
				if trole is not None:
					corpoch.dbot.tasks.set_group_role(ply.user, ply.tournament.guild, trole)

@admin.register(Qualifier)
class TournamentQualifierAdmin(admin.ModelAdmin):
	list_display = ('id', 'tournament')
	list_filter = ['tournament']
	actions = ['submit_final_scores']

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == "player":
			if 'object_id' in request.resolver_match.kwargs:
				group = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs["queryset"] = group.tournament.players
			else:
				kwargs["queryset"] = GroupSeed.objects.none()
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

	@admin.action(description="Submit Final Top Scores")
	def submit_final_scores(modeladmin, request, queryset):
		sheet = GSheets(fin=True)
		sheet.login()
		for quali in queryset:
			for ply in TournamentPlayer.objects.all().filter(tournament=quali.tournament):
				objs = QualifierSubmission.objects.all().filter(player=ply)
				subs = sorted(objs, key=lambda i: i.steg.players[0].score)
				if len(subs) >= quali.required_submissions:
					print(f"Submitting Final Score for {ply} - {subs[-1].steg.players[0].score}")
					sheet.set_submission(subs[-1])
					sheet.submit_qualifier()

class SeedingInline(SortableStackedInline):
	model = GroupSeed
	extra = 1

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == "player":
			if 'object_id' in request.resolver_match.kwargs:
				group = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs["queryset"] = group.tournament.players
			else:
				kwargs["queryset"] = GroupSeed.objects.none()
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Group)
class GroupAdmin(SortableAdminBase, admin.ModelAdmin):
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
		return super(GroupAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

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
class QualifierSubmissionAdmin(admin.ModelAdmin):
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

class RoundsInline(SortableStackedInline):
	model = MatchRound
	formfield_overrides = { fields.PydanticSchemaField: {"widget": JSONFormWidget}, }
	extra = 0

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == "winner" or db_field.name == "loser" or db_field.name == 'picked':
			if 'object_id' in request.resolver_match.kwargs:
				match = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = TournamentPlayer.objects.all().filter(id__in=match.players.all().values("player"))
			else:
				kwargs["queryset"] = TournamentPlayer.objects.none()
		if db_field.name == 'chart':
			if 'object_id' in request.resolver_match.kwargs:
				match = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs["queryset"] = match.bracket.setlist.all()
			else:
				kwargs["queryset"] = GroupSeed.objects.none()
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

class BansInline(SortableStackedInline):
	model = MatchBan
	extra = 0

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == "player":
			if 'object_id' in request.resolver_match.kwargs:
				match = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = match.players.all()
			else:
				kwargs["queryset"] = GroupSeed.objects.none()
		if db_field.name == 'chart':
			if 'object_id' in request.resolver_match.kwargs:
				match = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs["queryset"] = match.bracket.setlist.all()
			else:
				kwargs["queryset"] = TournamentPlayer.objects.none()
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Match)
class MatchAdmin(SortableAdminBase, admin.ModelAdmin):
	list_display = ('__str__', 'group', '_match_players', 'score', 'started_on', 'ended_on', 'complete', 'finished', 'submitted')
	inlines = [BansInline, RoundsInline]
	list_per_page = 16
	actions = ['set_unsubmitted',"reread_steg", "resubmit_gsheet", "resubmit_discord"]

	def _match_players(self, obj):
		retList = []
		for seed in obj.players.iterator():
			retList.append(str(seed))
		return " vs ".join(retList)

	def formfield_for_manytomany(self, db_field, request, **kwargs):
		if db_field.name == "players":
			if 'object_id' in request.resolver_match.kwargs:
				match = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = match.group.seeding.all()
			else:
				kwargs["queryset"] = GroupSeed.objects.none()
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == "winner" or db_field.name == "loser":
			if 'object_id' in request.resolver_match.kwargs:
				match = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = TournamentPlayer.objects.all().filter(id__in=match.players.all().values("player"))
			else:
				kwargs["queryset"] = TournamentPlayer.objects.none()
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

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

	@admin.action(description="Refresh Discord Message")
	def resubmit_discord(modeladmin, request, queryset):
		for match in queryset:
			corpoch.dbot.tasks.refresh_match_message(match.id)
