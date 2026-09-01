from django.contrib import admin
from django.forms import ModelForm

from adminsortable2.admin import CustomInlineFormSet, SortableAdminBase, SortableStackedInline, SortableAdminMixin
from django_jsonform.widgets import JSONFormWidget
from django_pydantic_field import fields

import corpoch.dbot.tasks
from corpoch.models import TournamentConfig, Match, MatchRound, MatchBan
import corpoch.tasks

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
		if 'object_id' in request.resolver_match.kwargs:
			obj = self.parent_model.objects.get(pk=request.resolver_match.kwargs['object_id'])
		else:
			obj = None

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
		if db_field.name == "referee":
			if 'object_id' in request.resolver_match.kwargs:
				match = self.model.objects.get(pk=request.resolver_match.kwargs['object_id'])
				queryset =  match.tournament.guild.referees.all() | match.tournament.guild.admins.all()
				if match.referee:
					queryset = queryset | DiscordUser.objects.filter(pk=match.referee.id)
				queryset = queryset.distinct()
				kwargs['queryset'] = queryset
			else:
				kwargs['queryset'] = DiscordUser.objects.none()
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
