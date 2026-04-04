from django.core.management.base import BaseCommand
from corpoch.models import TournamentPlayer
from corpoch.types import PlayerConfig, CH_Name

class Command(BaseCommand):
    help = 'Migrates existing ch_name strings into the new config JSON array.'

    def handle(self, *args, **kwargs):
        players = TournamentPlayer.objects.all()
        players_to_update = []

        for player in players:
            ch_name_str = player.ch_name

            if ch_name_str:
                new_ch_name = CH_Name(ch_name=ch_name_str, is_primary=True)
                new_config = PlayerConfig(names_list=[new_ch_name])
                player.config = new_config
                players_to_update.append(player)

        if players_to_update:
            TournamentPlayer.objects.bulk_update(players_to_update, ['config'])
            self.stdout.write(self.style.SUCCESS(f'Successfully migrated {len(players_to_update)} players!'))
        else:
            self.stdout.write(self.style.WARNING('No players needed updating.'))