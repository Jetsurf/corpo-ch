from django_pydantic_field.rest_framework import SchemaField
from rest_framework import serializers

from corpoch import models as corpomodels
from corpoch.dbot import models as dbotmodels
from corpoch.types import StegScreenshot

class DiscordUserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = corpomodels.DiscordUser
        fields = ['id', 'global_name', 'avatar', 'public_flags']

class DiscordChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = dbotmodels.Channels
        fields = '__all__'

class DiscordRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = dbotmodels.Roles
        fields = '__all__'

class DiscordGuildSerializer(serializers.ModelSerializer):
    class Meta:
        model = dbotmodels.Guilds
        fields = '__all__'

class TournamentSerializer(serializers.ModelSerializer):
    class Meta:
        model = corpomodels.Tournament
        fields = '__all__'

class TournamentPlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = corpomodels.TournamentPlayer
        fields = '__all__'

class BracketRulesSerializer(serializers.ModelSerializer):
    class Meta:
        model = corpomodels.BracketRules
        fields = '__all__'

class BracketSerializer(serializers.ModelSerializer):
    tournament = TournamentSerializer()
    ruleset = BracketRulesSerializer()
    class Meta:
        model = corpomodels.Bracket
        fields = '__all__'

class GroupSeedSerializer(serializers.ModelSerializer):
    player = TournamentPlayerSerializer()
    class Meta:
        model = corpomodels.GroupSeed
        fields = '__all__'

class GroupSerializer(serializers.ModelSerializer):
    seeding = GroupSeedSerializer(many=True)
    class Meta:
        model = corpomodels.Group
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

class MatchSerializer(serializers.ModelSerializer):
    players = GroupSeedSerializer(many=True)
    match_rounds = MatchRoundSerializer(many=True)
    match_bans = MatchBanSerializer(many=True)
    class Meta:
        model = corpomodels.Match
        fields = '__all__'

class CHIconSerializer(serializers.ModelSerializer):
    class Meta:
        model = corpomodels.CHIcon
        fields = '__all__'

class ChartSerializer(serializers.ModelSerializer):
    icon = CHIconSerializer()
    brackets = BracketSerializer(many=True)
    class Meta:
        model = corpomodels.Chart
        fields = '__all__'

class MatchSerializer(serializers.ModelSerializer):
    players = GroupSeedSerializer(many=True)
    match_rounds = MatchRoundSerializer(many=True)
    match_bans = MatchBanSerializer(many=True)
    class Meta:
        model = corpomodels.Match
        fields = '__all__'

class QualifierSerializer(serializers.ModelSerializer):
    class Meta:
        model = corpomodels.Qualifier
        fields = '__all__'

class QualifierSubmissionSerializer(serializers.ModelSerializer):
    steg = SchemaField(StegScreenshot)
    class Meta:
        model = corpomodels.QualifierSubmission
        fields = '__all__'