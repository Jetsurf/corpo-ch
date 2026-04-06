from django.contrib.auth.models import Group, User
from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view

import corpoch.models as corpomodels
import corpoch.dbot.models as dbotmodels
from corpoch.api import serializers 

class DiscordUserViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets discord users associated with objects.
	"""
	queryset = corpomodels.DiscordUser.objects.all().order_by("id")
	serializer_class = serializers.DiscordUserSerializer

class DiscordGuildViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets Guilds tournaments have been ran in.
	"""
	queryset = dbotmodels.Guilds.objects.all().order_by("id")
	serializer_class = serializers.DiscordGuildSerializer

	@api_view
	def get_guild(self, guild: dbotmodels.Guilds) -> dbotmodels.Guilds | None:
		try:
			return dbotmodels.Guilds.objects.get(id=guild.id)
		except dbotmodels.Guilds.DoesNotExist:
			return None

class DiscordChannelViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets Guild channels that are associated with Tournamentss.
	"""
	queryset = dbotmodels.Channels.objects.all().order_by("id")
	serializer_class = serializers.DiscordChannelSerializer

	@api_view
	def get_channel(self, channel: dbotmodels.Channels) -> dbotmodels.Channels | None:
		try:
			return dbotmodels.Channels.objects.get(id=channel.id)
		except dbotmodels.Channels.DoesNotExist:
			return None

class DiscordRoleViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets Roles associated with Tournaments.
	"""
	queryset = dbotmodels.Roles.objects.all().order_by("id")
	serializer_class = serializers.DiscordRoleSerializer

	@api_view
	def get_role(self, role: dbotmodels.Roles) -> dbotmodels.Roles | None:
		try:
			return dbotmodels.Roles.objects.get(id=role.id)
		except dbotmodels.Roles.DoesNotExist:
			return None

class BracketViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Brackets.
	"""
	queryset = corpomodels.Bracket.objects.all().order_by("id")
	serializer_class = serializers.BracketSerializer

	@api_view
	def get_bracket(self, bracket: corpomodels.Bracket) -> corpomodels.Bracket | None:
		try:
			return corpomodels.Bracket.objects.get(id=bracket.id)
		except corpomodels.Bracket.DoesNotExist:
			return None

class GroupViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Groups.
	"""
	queryset = corpomodels.Group.objects.all().order_by("id")
	serializer_class = serializers.GroupSerializer

	@api_view
	def get_match(self, group: corpomodels.Group) -> corpomodels.Group | None:
		try:
			return corpomodels.Group.objects.get(id=group.id)
		except corpomodels.Group.DoesNotExist:
			return None

class GroupSeedViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets GroupSeed objects, which are a Players seeding for a specific tournament group.
	"""
	queryset = corpomodels.GroupSeed.objects.all().order_by("id")
	serializer_class = serializers.GroupSeedSerializer

	@api_view
	def get_match(self, seed: corpomodels.GroupSeed) -> corpomodels.GroupSeed | None:
		try:
			return corpomodels.GroupSeed.objects.get(id=seed.id)
		except corpomodels.Group.DoesNotExist:
			return None

class MatchViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Matches.
	"""
	queryset = corpomodels.Match.objects.all().order_by("id")
	serializer_class = serializers.MatchSerializer

	@api_view
	def get_match(self, match: corpomodels.Match) -> corpomodels.Match | None:
		try:
			return corpomodels.Match.objects.get(id=match.id)
		except corpomodels.Match.DoesNotExist:
			return None

class TournamentPlayerViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Players.
	"""
	queryset = corpomodels.TournamentPlayer.objects.all().order_by("id")
	serializer_class = serializers.TournamentPlayerSerializer

	@api_view
	def get_player(self, player: corpomodels.TournamentPlayer) -> corpomodels.TournamentPlayer | None:
		try:
			return TournamentPlayer.objects.get(id=player.id)
		except TournamentPlayer.DoesNotExist:
			return None
