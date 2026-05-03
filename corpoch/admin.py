import json, time
from itertools import chain

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from django.forms import ModelForm
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.html import format_html

from adminsortable2.admin import CustomInlineFormSet, SortableAdminBase, SortableStackedInline, SortableAdminMixin
from django_jsonform.widgets import JSONFormWidget
from django_pydantic_field import fields
from solo.admin import SingletonModelAdmin

from corpoch.forms import TournamentPlayerForm
from corpoch.models import Chart, Tournament, TournamentConfig, BracketRules, Bracket, Qualifier, TournamentPlayer, GroupSeed, MatchRound, CHIcon
from corpoch.models import Match, Group, QualifierSubmission, CH_MODIFIERS, MatchBan, GSheetAPI, DiscordUser
from corpoch.dbot.models import Guilds, Channels, Roles
from corpoch.providers import EncoreClient, GSheets
from corpoch import __version__ as version
from corpoch import settings
import corpoch.dbot.tasks
import corpoch.tasks

admin.site.site_header = f'Corpo CH Admin {version}{f' - DEV' if settings.DEBUG else ''}'
admin.site.site_title = 'Corpo CH'
admin.site.register(GSheetAPI, SingletonModelAdmin)

@admin.register(DiscordUser)
class DiscordUserAdmin(admin.ModelAdmin):
	model = DiscordUser
	list_display = ('_avatar', 'id', 'global_name')
	readonly_fields = ['global_name', 'mfa_enabled', '_id', 'avatar', 'locale', 'flags', 'public_flags', 'last_login', 'date_joined']
	exclude = ['password', 'first_name', 'last_name', 'email', 'username']
	search_fields = ['id', "global_name"]
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
	list_display = ('_icon','name',  '_bracket', 'charter', 'artist', 'album', 'speed', '_modifiers', 'tiebreaker', 'game_version')
	list_filter = ['brackets__tournament', 'tiebreaker', 'boss']
	actions = ['run_encore_import', 'import_song_ini']
	readonly_fields = ['_icon', 'game_version']
	search_fields = ('name', 'charter')
	filter_horizontal = ['brackets']

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

	def game_version(self, obj):
		return obj.game_version

	@mark_safe
	def _icon(self, obj):
		if obj.icon:
			return f'<img src="{obj.icon.img.url}" width="24" height="24"'
		else:
			return "None"

	def get_readonly_fields(self, request, obj=None):
		if not obj or request.user.is_superuser:
			return self.readonly_fields

		for bracket in obj.brackets.all():
			try:
				is_staff = bracket.tournament.guild.admins.get(id=request.user.id)
				return self.readonly_fields
			except DiscordUser.DoesNotExist:
				continue

		return list(chain(self.readonly_fields, ['id', 'name', 'artist', 'album', 'charter', 'boss', 'tiebreaker', 'difficulty', 'instrument', 'modifiers', 'speed', 'category', 'brackets', 'md5', 'blake3', 'url', 'icon', 'sngfile']))

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		if request.user.is_superuser:
			return qs
		for obj in qs:
			for bracket in obj.brackets.all():
				if bracket.revealed:
					break
				else:
					try:
						is_admin = bracket.tournament.guild.admins.get(id=request.user.id)
						is_player = bracket.tournament.players.get(user=is_admin)
						qs = qs.all().exclude(id=obj.id) #If staff user in tournament, hide chart
					except DiscordUser.DoesNotExist:
						qs = qs.all().exclude(id=obj.id)
					except TournamentPlayer.DoesNotExist:
						pass
		return qs

	@admin.action(description="Run Encore import")
	def run_encore_import(modeladmin, request, queryset):
		for chart in queryset:
			corpoch.tasks.encore_import.apply_async(args=[chart.id])

	@admin.action(description="Import data from song.ini")
	def import_song_ini(modeladmin, request, queryset):
		for chart in queryset:
			corpoch.tasks.chart_songini_import.apply_async(args=[chart.id])

class TournamentConfigInline(admin.StackedInline):
	model = TournamentConfig
	extra = 0

	def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
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
			if role:
				for bracket in tourney.brackets.all():
					for group in bracket.groups.all():
						for seed in group.seeding.all():
							ply = seed.player.user
							corpoch.dbot.tasks.set_group_role(ply.id, guild.id, role.id)

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

class BracketRulesInline(admin.StackedInline):
	model = BracketRules
	extra = 0

	def get_readonly_fields(self, request, obj=None):
		if not obj or request.user.is_superuser:
			return ()
		try:
			is_staff = obj.tournament.guild.admins.get(id=request.user.id)
			return ()
		except DiscordUser.DoesNotExist:
			if obj == None or len(obj.setlist.all().filter(boss=True)) == 0:
				return ('num_players', 'num_bans', 'num_rounds', 'ban_ruleset', 'pick_ruleset', 'tb_ruleset',)
			else:
				return ('num_players', 'num_bans', 'num_rounds', 'boss_active', 'boss_bannable', 'ban_ruleset', 'pick_ruleset', 'tb_ruleset',)

	def get_fields(self, request, obj=None):
		if obj == None or len(obj.setlist.all().filter(boss=True)) == 0:
			return ('num_players', 'num_bans', 'num_rounds', 'ban_ruleset', 'pick_ruleset', 'tb_ruleset',)
		else:
			return ('num_players', 'num_bans', 'num_rounds', 'boss_active', 'boss_bannable', 'ban_ruleset', 'pick_ruleset', 'tb_ruleset',)

@admin.register(Bracket)
class BracketAdmin(admin.ModelAdmin):
	list_display = ("_name", 'tournament')
	list_filter = ['tournament']
	inlines = [BracketRulesInline]
	actions = ['set_bracket_role']

	def _name(self, obj):
		return f"{obj}"

	def get_readonly_fields(self, request, obj=None):
		if not obj or request.user.is_superuser:
			return ()
		try:
			is_staff = obj.tournament.guild.admins.get(id=request.user.id)
			return ()
		except DiscordUser.DoesNotExist:
			return ('id', 'name', 'tournament', 'score_log', 'is_active', 'revealed', 'role')

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
			guild = bracket.tournament.guild
			role = bracket.role
			if role:
				for group in bracket.groups.all():
					for seed in group.seeding.all():
						ply = seed.player.user
						corpoch.dbot.tasks.set_group_role(ply.id, guild.id, role.id)

@admin.register(TournamentPlayer)
class TournamentPlayerAdmin(admin.ModelAdmin):
	form = TournamentPlayerForm
	list_display = ('user', 'tournament', 'display_exact_ch_name', 'is_active')
	list_filter = ['tournament', 'is_active']
	actions = ["set_tournament_roles"]
	readonly_fields = ("display_exact_ch_name",)
	search_fields = ('name',)
	fields = (
		'user',
		'name',
		'tournament',
		'display_exact_ch_name',
		'primary_ch_name_selection',
		'new_ch_name',
		'is_active',
		'config',
		'delete_ch_name',
	)

	def check_perm(self, request, obj):
		if not obj or request.user.is_superuser:
			return True
		try:
			is_staff = obj.tournament.guild.admins.get(id=request.user.id)
			return True
		except DiscordUser.DoesNotExist:
			return False

	def has_add_permission(self, request, obj=None):
		return self.check_perm(request, obj)

	def has_delete_permission(self, request, obj=None):
		return self.check_perm(request, obj)

	def has_change_permission(self, request, obj=None):
		return self.check_perm(request, obj)

	@admin.display(description='Clone Hero Name', ordering='ch_name')
	def display_exact_ch_name(self, obj):
		if not obj.ch_name:
			return "-"

		return format_html(
			'<span style="white-space: pre-wrap; background-color: rgba(128, 128, 128, 0.2); padding: 2px 4px; border-radius: 3px; font-family: monospace;">{}</span>',
			obj.ch_name
		)

	@admin.action(description="Set tournament roles")
	def set_tournament_roles(modeladmin, request, queryset):
		for ply in queryset:
			guild = ply.tournament.guild
			for seed in ply.group_seeding.all():
				grole = seed.group.role if seed.group.role else None
				brole = seed.group.bracket.role if seed.group.bracket.role else None
				trole = tourney.role if tourney.role else None
				if grole is not None:
					corpoch.dbot.tasks.set_group_role(ply.user.id, guild.id, grole.id)
				if brole is not None:
					corpoch.dbot.tasks.set_group_role(ply.user.id, guild.id, brole.id)
				if trole is not None:
					corpoch.dbot.tasks.set_group_role(ply.user.id, guild.id, trole.id)

@admin.register(Qualifier)
class QualifierAdmin(admin.ModelAdmin):
	list_display = ('id', 'tournament', '_players', '_submissions')
	list_filter = ['tournament']
	actions = ['submit_final_scores']

	def _players(self, obj):
		return QualifierSubmission.objects.all().filter(qualifier__tournament=obj.tournament).values('player').distinct().count()

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
		for quali in queryset:
			corpoch.tasks.submit_final_sheet.apply_async(args=[quali.id])

class SeedingInline(SortableStackedInline):
	model = GroupSeed
	extra = 0

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == "player":
			if 'object_id' in request.resolver_match.kwargs:
				group = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs["queryset"] = group.bracket.tournament.players.all()
			else:
				kwargs["queryset"] = GroupSeed.objects.none()
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

	def check_perm(self, request):
		obj = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
		if not obj or request.user.is_superuser:
			return True
		try:
			is_staff = obj.tournament.guild.admins.get(id=request.user.id)
			return True
		except DiscordUser.DoesNotExist:
			return False

	def has_add_permission(self, request, obj=None):
		return self.check_perm(request)

	def has_delete_permission(self, request, obj=None):
		return self.check_perm(request)

	def has_change_permission(self, request, obj=None):
		return self.check_perm(request)

	def get_readonly_fields(self, request, obj=None):
		if not obj or request.user.is_superuser:
			return ()
		try:
			is_staff = obj.tournament.guild.admins.get(id=request.user.id)
			return ()
		except DiscordUser.DoesNotExist:
			return ('id', 'seed', 'player', 'eliminated',)

@admin.register(Group)
class GroupAdmin(SortableAdminBase, admin.ModelAdmin):
	list_display = ('name', 'bracket_name','tournament', 'active_count', 'player_count')
	list_filter = ('bracket__tournament',)
	inlines = [SeedingInline]
	search_fields = ('bracket',)
	list_per_page = 32
	actions = ['set_group_role']

	def tournament(self, obj):
		return obj.bracket.tournament.short_name

	def bracket_name(self, obj):
		return obj.bracket.name

	def active_count(self, obj):
		return obj.seeding.all().filter(player__is_active=True, eliminated=False).count()

	def player_count(self, obj):
		return obj.seeding.all().count()

	def check_perm(self, request, obj=None):
		if not obj or request.user.is_superuser:
			return True
		try:
			is_staff = obj.bracket.tournament.guild.admins.get(id=request.user.id)
			return True
		except DiscordUser.DoesNotExist:
			return False

	def has_add_permission(self, request, obj=None):
		return self.check_perm(request, obj)

	def has_delete_permission(self, request, obj=None):
		return self.check_perm(request, obj)

	def has_change_permission(self, request, obj=None):
		return self.check_perm(request, obj)

	def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
		if db_field.name == 'bracket':
			if 'object_id' in request.resolver_match.kwargs:
				model = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = Bracket.objects.all().filter(tournament=model.bracket.tournament)
			else:
				kwargs['queryset'] = Bracket.objects.all().filter(tournament__active=True)
		if db_field.name == "role":
			if 'object_id' in request.resolver_match.kwargs:
				group = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = Roles.objects.filter(guild=group.bracket.tournament.guild)
			else:
				kwargs["queryset"] = Roles.objects.none()
		return super(GroupAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

	@admin.action(description="Set group role for players")
	def set_group_role(modeladmin, request, queryset):
		for group in queryset:
			guild = group.bracket.tournament.guild
			role = group.role
			if role:
				for seed in group.seeding.all():
					ply = seed.player.user
					corpoch.dbot.tasks.set_group_role(ply.id, guild.id, role.id)

@admin.register(QualifierSubmission)
class QualifierSubmissionAdmin(admin.ModelAdmin):
	list_display = ('id', 'qualifier', 'player_ch_name', 'score', '_miss', '_hit', '_excess', '_ghosts', '_phrases', 'submitted')
	list_filter = ["qualifier"]
	search_fields = ['id', 'player__name']
	formfield_overrides = { fields.PydanticSchemaField: {"widget": JSONFormWidget}, }
	actions = ['set_unsubmitted',"reread_steg", "resubmit_gsheet"]

	def tournament(self, obj):
		return obj.qualifier.tournament.short_name

	def player_ch_name(self, obj):
		return obj.player.ch_name

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

	def get_form(self, request, obj=None, **kwargs):
		form = super(QualifierSubmissionAdmin, self).get_form(request, obj=obj, **kwargs)
		user = request.user
		staff = False
		try:
			is_staff = obj.qualifier.tournament.guild.admins.get(id=user.id)
			staff = True
		except DiscordUser.DoesNotExist:
			pass
		if not staff or (obj and not obj.screenshot):
			form.base_fields['steg'].disabled = True
		return form

	def get_readonly_fields(self, request, obj=None):
		if not obj or request.user.is_superuser:
			return ()
		try:
			is_staff = obj.qualifier.tournament.guild.admins.get(id=request.user.id)
			return ()
		except DiscordUser.DoesNotExist:
			return ('id', 'player', 'screenshot', 'qualifier', 'submitted')

	def get_queryset(self, request):
		qs = super().get_queryset(request)
		if request.user.is_superuser:
			return qs
		for obj in qs:
			staff = False
			try:
				is_admin = obj.qualifier.tournament.guild.admins.get(id=request.user.id)
				staff = True
			except DiscordUser.DoesNotExist:
				pass

			if not staff and obj.qualifier.end_time > timezone.now():
				qs = qs.all().exclude(id=obj.id)
		return qs

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == "player":
			if 'object_id' in request.resolver_match.kwargs:
				sub = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				kwargs['queryset'] = TournamentPlayer.objects.all().filter(tournament=sub.qualifier.tournament)
			else:
				kwargs["queryset"] = TournamentPlayer.objects.all()
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

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
		for submission in queryset:
			corpoch.tasks.update_gsheet.apply_async(args=[submission.id])

class RoundsForm(ModelForm):
	class Meta:
		model = MatchRound
		fields = '__all__'

	def __init__(self, *args, **kwargs):
		super(RoundsForm, self).__init__(*args, **kwargs)
		if self.instance and self.instance.pk:
			if not self.instance.screenshot and 'steg' in self.fields:
				self.fields['steg'].disabled = True
		return

class RoundsInline(SortableStackedInline):
	model = MatchRound
	formfield_overrides = { fields.PydanticSchemaField: {"widget": JSONFormWidget}, }
	extra = 0

	def get_formset(self, request, obj=None, **kwargs):
		formset = super().get_formset(request, obj, **kwargs)
		if request.user.is_superuser:
			return formset

		staff, ref = False, False
		if obj:
			try:
				is_staff = obj.group.tournament.guild.admins.get(id=request.user.id)
				staff = True
			except DiscordUser.DoesNotExist:
				pass
			try:
				is_ref = obj.group.tournament.guild.referees.get(id=request.user.id)
				ref = True
			except DiscordUser.DoesNotExist:
				pass

		if not staff and not ref:
			if 'steg' in formset.form.base_fields:
				formset.form.base_fields['steg'].disabled = True

		return formset

	def get_readonly_fields(self, request, obj=None):
		if not obj or request.user.is_superuser:
			return ('created',)
		staff = False
		try:
			is_staff = obj.tournament.guild.admins.get(id=request.user.id)
			return ('created',)
		except DiscordUser.DoesNotExist:
			return ('id', 'num', 'match', 'picked', 'chart', 'winner', 'loser', 'screenshot', 'created')

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

	def check_perm(self, request):
		obj = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
		if not obj or request.user.is_superuser:
			return True
		try:
			is_staff = obj.tournament.guild.admins.get(id=request.user.id)
			return True
		except DiscordUser.DoesNotExist:
			pass
		try:
			is_ref = obj.tournament.guild.referees.get(id=request.user.id)
			return True
		except DiscordUser.DoesNotExist:
			return False

	def has_add_permission(self, request, obj=None):
		return self.check_perm(request)

	def has_delete_permission(self, request, obj=None):
		return self.check_perm(request)

	def has_change_permission(self, request, obj=None):
		return self.check_perm(request)

	def formfield_for_foreignkey(self, db_field, request, **kwargs):
		if db_field.name == "player":
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
				kwargs["queryset"] = Chart.objects.none()
		return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Match)
class MatchAdmin(SortableAdminBase, admin.ModelAdmin):
	list_display = ('__str__', 'group', '_match_players', 'score', 'started_on', 'ended_on', 'complete', 'finished', 'submitted')
	list_filter = ('group__bracket__tournament',)
	inlines = [BansInline, RoundsInline]
	list_per_page = 25
	search_fields = ['id']
	actions = ['set_unsubmitted', "reread_steg", "resubmit_gsheet", "resubmit_discord"]

	def get_readonly_fields(self, request, obj=None):
		if request.user.is_superuser:
			return ('started_on',)
		try:
			is_ref = obj.group.tournament.guild.referees.get(id=request.user.id)
			return ('started_on',)
		except DiscordUser.DoesNotExist:
			pass
		try:
			is_admin = obj.group.tournament.guild.admins.get(id=request.user.id)
			return ('started_on',)
		except DiscordUser.DoesNotExist:
			return ('id', 'players', 'loser', 'winner', 'defer', 'group', 'started_on', 'ended_on', 'complete', 'finished', 'submitted', 'channel', 'message', 'referee', 'exhibition')			

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
		for match in queryset:
			corpoch.tasks.update_gsheet.apply_async(args=[match.id])

	@admin.action(description="Refresh Discord Message")
	def resubmit_discord(modeladmin, request, queryset):
		for match in queryset:
			corpoch.dbot.tasks.refresh_match_message(match.id)
