from datetime import timedelta

from django.core.paginator import Paginator
from django.utils import timezone

from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

import corpoch.models as corpomodels
import corpoch.dbot.models as dbotmodels
from corpoch.api import serializers 

class LargeResultsSetPagination(PageNumberPagination):
	page_size = 25
	page_query_param = "page"

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

class DiscordChannelViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets Guild channels that are associated with Tournamentss.
	"""
	queryset = dbotmodels.Channels.objects.all().order_by("id")
	serializer_class = serializers.DiscordChannelSerializer

class DiscordRoleViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets Roles associated with Tournaments.
	"""
	queryset = dbotmodels.Roles.objects.all().order_by("id")
	serializer_class = serializers.DiscordRoleSerializer

class TournamentViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Tournaments.
	"""
	queryset = corpomodels.Tournament.objects.all().order_by("id")
	serializer_class = serializers.TournamentSerializer

class BracketRulesViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Bracket Rules.
	"""
	queryset = corpomodels.BracketRules.objects.all()
	serializer_class = serializers.BracketRulesSerializer

class BracketViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Brackets.
	"""
	queryset = corpomodels.Bracket.objects.all().order_by("id")
	serializer_class = serializers.BracketSerializer

class GroupViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Groups.
	"""
	queryset = corpomodels.Group.objects.all().order_by("id")
	serializer_class = serializers.GroupSerializer

class GroupSeedViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets GroupSeed objects, which are a Players seeding for a specific tournament group.
	"""
	queryset = corpomodels.GroupSeed.objects.all().order_by("seed")
	serializer_class = serializers.GroupSeedSerializer

class MatchViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Matches.
	"""
	queryset = corpomodels.Match.objects.all().order_by("ended_on")
	serializer_class = serializers.MatchSerializerLight
	detail_serializer_class = serializers.MatchSerializer
	pagination_class = LargeResultsSetPagination

	def retrieve(self, request, *args, **kwargs):
		instance = self.get_object()
		serializer = self.get_serializer(instance)
		for rnd in serializer.data['match_rounds']:
			#Going to need to change for >2 players
			if not instance.high_seed.check_ch_name(rnd['steg']['players'][0]['profile_name']): 
				rnd['steg']['players'].reverse()
		return Response(serializer.data, status=200)

	def get_serializer_class(self):
		if self.action == 'retrieve':
			return self.detail_serializer_class
		else:
			return self.serializer_class

class CHIconViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Chart Icons.
	"""
	queryset = corpomodels.CHIcon.objects.all()
	serializer_class = serializers.CHIconSerializer

class ChartViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Charts.
	"""
	queryset = corpomodels.Chart.objects.all().filter(brackets__revealed=True).order_by("id")
	serializer_class = serializers.ChartSerializer

class TournamentPlayerViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Players.
	"""
	queryset = corpomodels.TournamentPlayer.objects.all().order_by("id")
	serializer_class = serializers.TournamentPlayerSerializer

class QualifierSubmissionViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Tournament Qualifier Submissions for finished Qualifiers.
	"""
	queryset = corpomodels.QualifierSubmission.objects.all().filter(qualifier__end_time__lt=timezone.now() + timedelta(hours=2)).order_by("-submit_time")
	serializer_class = serializers.QualifierSubmissionSerializer

class QualifierViewSet(viewsets.ModelViewSet):
	"""
	API endpoint that gets and edits Tournament Qualifiers.
	"""
	queryset = corpomodels.Qualifier.objects.all().order_by("id")
	serializer_class = serializers.QualifierSerializer
