from django.core.management.base import BaseCommand
from corpoch.models import TournamentPlayer

class Command(BaseCommand):
    help = 'Migrates existing ch_name strings into the new config JSON array.'

    def handle(self, *args, **kwargs):
        players = TournamentPlayer.objects.all()
        players_to_update = []

        for player in players:
            if not player.config or not isinstance(player.config, list):

                name_to_migrate = player.ch_name
                if not name_to_migrate or name_to_migrate == "</Null>":
                    name_to_migrate = "</Null>"

                player.config = [
                    {
                        "ch_name": name_to_migrate,
                        "is_primary": True
                    }
                ]

                players_to_update.append(player)

        if players_to_update:
            TournamentPlayer.objects.bulk_update(players_to_update, ['config'])
            self.stdout.write(self.style.SUCCESS(f'Successfully migrated {len(players_to_update)} players!'))
        else:
            self.stdout.write(self.style.WARNING('No players needed updating.'))