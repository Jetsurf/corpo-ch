from django.core.management.base import BaseCommand
from corpoch.models import Tournament, Bracket, Group, TournamentPlayer, DiscordUser, Match
from corpoch.types import Stats

class Command(BaseCommand):
    help = 'Flushes all stats objects and sets all matches to unprocessed'

    def handle(self, *args, **kwargs):
        for tournament in Tournament.objects.all():
            tournament.stats = Stats()
            tournament.save()

        for bracket in Bracket.objects.all():
            bracket.stats = Stats()
            bracket.save()

        for group in Group.objects.all():
            group.stats = Stats()
            group.save()

        for player in TournamentPlayer.objects.all():
            player.stats = Stats()
            player.save()

        for user in DiscordUser.objects.all():
            user.stats = Stats()
            user.save()

        for match in Match.objects.all():
            match.processed = False
            match.save()
