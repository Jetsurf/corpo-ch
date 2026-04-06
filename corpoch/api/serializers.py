from django_pydantic_field.rest_framework import SchemaField
from rest_framework import serializers

from corpoch import models as corpomodels
from corpoch.dbot import models as dbotmodels
from corpoch.types import StegScreenshot

class DiscordUserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = corpomodels.DiscordUser
        fields = ['id', 'global_name', 'avatar', 'public_flags']

class DiscordChannelSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = dbotmodels.Channels
        fields = '__all__'

class DiscordRoleSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = dbotmodels.Roles
        fields = '__all__'

class DiscordGuildSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = dbotmodels.Guilds
        fields = '__all__'

class BracketSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = corpomodels.Bracket
        fields = '__all__'

class GroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = corpomodels.Group
        fields = '__all__'

class GroupSeedSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = corpomodels.GroupSeed
        fields = '__all__'

class MatchBanSerializer(serializers.ModelSerializer):
    class Meta:
        model = corpomodels.MatchBan
        fields = '__all__'

class MatchRoundSerializer(serializers.ModelSerializer):
    steg = SchemaField(StegScreenshot)
    class Meta:
        model = corpomodels.MatchRound
        fields = '__all__'

class MatchSerializer(serializers.HyperlinkedModelSerializer):
    match_rounds = MatchRoundSerializer(many=True)
    match_bans = MatchBanSerializer(many=True)
    class Meta:
        model = corpomodels.Match
        fields = '__all__'

class TournamentPlayerSerializer(serializers.ModelSerializer):

    class Meta:
        model = corpomodels.TournamentPlayer
        fields = '__all__'

