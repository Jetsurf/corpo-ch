import json, time

from adminsortable2.admin import CustomInlineFormSet, SortableAdminBase, SortableStackedInline, SortableAdminMixin

from django_pydantic_field import fields
from django.contrib import admin
from django_jsonform.widgets import JSONFormWidget
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count

from corpoch.models import Chart, Tournament, TournamentConfig, BracketRules, Bracket, Qualifier, TournamentPlayer, GroupSeed, MatchRound, CHIcon
from corpoch.models import Match, Group, QualifierSubmission, CH_MODIFIERS, MatchBan, GSheetAPI, DiscordUser
from corpoch.dbot.models import Guilds, Channels, Roles
from corpoch.providers import EncoreClient, GSheets
from django.utils.html import mark_safe
import corpoch.dbot.tasks

@admin.register(GSheetAPI)
class GSheetAPIAdmin(admin.ModelAdmin):
	pass

@admin.register(DiscordUser)
class DiscordUserAdmin(admin.ModelAdmin):
	model = DiscordUser
	list_display = ('_avatar', 'id', 'global_name')
	readonly_fields = ['global_name', 'mfa_enabled', '_id', 'avatar', 'locale', 'flags', 'public_flags', 'last_login', 'date_joined']
	exclude = ['password', 'first_name', 'last_name', 'email', 'username']
	actions = ['update_discord_user']

	def _id(self, obj):
		return str(obj.id)

	@mark_safe
	def _avatar(self, obj):
		return f'<img src="{obj.avatar}" width="24" height="24"'

	@admin.action(description="Update Discord Info")
	def update_discord_user(modeladmin, request, queryset):
		for user in queryset:
			corpoch.dbot.tasks.update_user(user.id)

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
		if obj.icon:
			return f'<img src="{obj.icon.img.url}" width="24" height="24"'
		else:
			return "None"

	@admin.action(description="Run Encore import")
	def run_encore_import(modeladmin, request, queryset):
		encore = EncoreClient()
		for chart in queryset:
			search = encore.search(chart.encore_search_query)
			i = 0 
			if len(search.data) == 0:
				print(f"Chart {chart.name} encore lookup with query {chart.encore_search_query} failed with query {search}")
				continue
			if len(search.data) > 1:
				print(f"Chart {chart.name} returned multiple results")
				for j, cht in enumerate(search.data):
					if chart.blake3 == cht.md5:
						i = j
						break

			encoreChart = search.data[i]
			chart.sngfile.save(f"{encoreChart.name}.sng", encore.download_from_chart(encoreChart))
			chart.save()

	@admin.action(description="Import data from song.ini")
	def import_song_ini(modeladmin, request, queryset):
		from corpoch.utils.snghandler import SNGHandler
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

	def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
		if db_field.name == "ref_role":
			if 'object_id' in request.resolver_match.kwargs:
				conf = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = Roles.objects.all().filter(guild=conf.tournament.guild)
			else:
				kwargs["queryset"] = Roles.objects.none()
		if db_field.name == "proof_channel":
			if 'object_id' in request.resolver_match.kwargs:
				conf = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = Channels.objects.all().filter(guild=conf.tournament.guild)
			else:
				kwargs["queryset"] = Channels.objects.none()
		return super(TournamentConfigInline, self).formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
	list_display = ('name', 'guild', 'active')
	inlines = [TournamentConfigInline]
	actions = ['set_tournament_role', 'set_players_active']

	def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
		if db_field.name == "role":
			if 'object_id' in request.resolver_match.kwargs:
				tournament = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = Roles.objects.all().filter(guild=tournament.guild)
			else:
				kwargs["queryset"] = Roles.objects.none()
		return super(TournamentAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

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

	def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
		if db_field.name == "role":
			if 'object_id' in request.resolver_match.kwargs:
				bracket = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = Roles.objects.all().filter(guild=bracket.tournament.guild)
			else:
				kwargs["queryset"] = Roles.objects.none()
		if db_field.name == "score_log":
			if 'object_id' in request.resolver_match.kwargs:
				bracket = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = Channels.objects.all().filter(guild=bracket.tournament.guild)
			else:
				kwargs["queryset"] = Channels.objects.none()
		return super(BracketAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

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
				grole = seed.group.role.id if seed.group.role else None
				brole = seed.group.bracket.role.id if seed.group.bracket.role else None
				trole = tourney.role.id if tourney.role.id else None
				print(f"Setting group roles for {ply.ch_name} {grole} - {brole} - {trole}")
				if grole is not None:
					corpoch.dbot.tasks.set_group_role(ply.user, ply.tournament.guild, grole)
				if brole is not None:
					corpoch.dbot.tasks.set_group_role(ply.user, ply.tournament.guild, brole)
				if trole is not None:
					corpoch.dbot.tasks.set_group_role(ply.user, ply.tournament.guild, trole)

@admin.register(Qualifier)
class QualifierAdmin(admin.ModelAdmin):
	list_display = ('id', 'tournament', '_players', '_submissions')
	list_filter = ['tournament']
	actions = ['submit_final_scores']

	def _players(self, obj):
		return TournamentPlayer.objects.all().filter(tournament=obj.tournament).count()

	def _submissions(self, obj):
		return QualifierSubmission.objects.filter(qualifier=obj).count()

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == "player":
			if 'object_id' in request.resolver_match.kwargs:
				group = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs["queryset"] = group.tournament.players
			else:
				kwargs["queryset"] = GroupSeed.objects.none()
		if db_field.name == "channel":
			if 'object_id' in request.resolver_match.kwargs:
				qualifier = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = Channels.objects.all().filter(guild=qualifier.tournament.guild)
			else:
				kwargs["queryset"] = Channels.objects.none()
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
		if db_field.name == "role":
			if 'object_id' in request.resolver_match.kwargs:
				group = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = Roles.objects.all().filter(guild=group.tournament.guild)
			else:
				kwargs["queryset"] = Roles.objects.none()
		return super(GroupAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

	@admin.action(description="Set group role for players")
	def set_group_role(modeladmin, request, queryset):
		for group in queryset:
			tourney = group.bracket.tournament
			role = group.role.id
			guild = tourney.guild.id
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
		return obj.steg.players[0].excess_hits if len(obj.steg.players) > 0 and obj.steg.players[0].excess_hits > -1 else '-'

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
	readonly_fields = ['created']
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
	readonly_fields = ['created']
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

	def get_queryset(self, request):
		 qs = super().get_queryset(request)
		 user = request.user
		 print(f"MATCHADMIN: VARS{vars(user)}")
		 return qs

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
		if db_field.name == "channel":
			if 'object_id' in request.resolver_match.kwargs:
				match = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = Channels.objects.all().filter(guild=match.tournament.guild)
			else:
				kwargs["queryset"] = Channels.objects.none()
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
