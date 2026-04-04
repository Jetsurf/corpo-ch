import uuid, typing, json, math, io, pydantic

from django.contrib import admin
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.serializers.json import DjangoJSONEncoder
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from django_pydantic_field import SchemaField
from encrypted_fields.fields import EncryptedJSONField, EncryptedTextField
from multiselectfield import MultiSelectField
from solo.models import SingletonModel

from corpoch import settings
from corpoch.managers import DiscordOAuth2Manager
from corpoch.utils.snghandler import SNGHandler
from corpoch.types import CH_INSTRUMENTS, CH_DIFFICULTIES, CH_MODIFIERS, CH_VERSIONS, CHART_CATEGORIES, TB_RULESETS, PICK_RULESETS, BAN_RULESETS, StegScreenshot, PlayerConfig, CH_Name
from corpoch.validators import validate_chart_file

def steg_upload_dir(self, filename):
	return f"matches/{str(self.match.group).replace(' ', '').replace(":", "")}/{self.match.id}/{filename}"

def quali_upload_dir(self, filename):
	return f"qualifiers/{str(self.qualifier).replace(' ', '').replace(':', '')}/{filename}"

class GSheetAPI(SingletonModel):
	api_key = EncryptedJSONField(null=False, blank=True, default=dict)
	sa_name = models.CharField(verbose_name="API Service Account Name", max_length=96)

	singleton_instance_id = 1

	def __str__(self):
		return "Google Sheets"

	class Meta:
		verbose_name = "Google Sheets API"

class DiscordUser(AbstractUser):
	objects = DiscordOAuth2Manager()
	id = models.BigIntegerField(primary_key=True, unique=True)
	global_name = models.CharField(max_length=255, null=True, blank=True)
	public_flags = models.IntegerField(null=True, blank=True)
	flags = models.IntegerField(null=True, blank=True)
	avatar = models.CharField(max_length=255, null=True, blank=True)
	locale = models.CharField(max_length=255, null=True, blank=True)
	mfa_enabled = models.BooleanField(default=False)
	last_login = models.DateTimeField(null=True, blank=True)

	username = None
	USERNAME_FIELD = 'id'
	REQUIRED_FIELDS = ()

	def __str__(self):
		if self.global_name:
			return self.global_name
		else:
			return str(self.id)

class DiscordToken(models.Model):
	access_token = EncryptedTextField(max_length=255)
	refresh_token = EncryptedTextField(max_length=255)
	user = models.OneToOneField("DiscordUser", null=True, on_delete=models.CASCADE, related_name="token")
	#This needs an expiry date field to trigger refreshes - refresh tokens need to be handled
	def __str__(self):
		return f"self.discord_user.global_name"

class CHIcon(models.Model):
	name = models.CharField(verbose_name="Name", blank=False, max_length=32, default="newicon", primary_key=True)
	img = models.ImageField(upload_to="chicons/", verbose_name="Image", null=True, blank=True)

	class Meta:
		verbose_name = "Chart Icon"
		verbose_name_plural = "Chart Icons"

	def __str__(self):
		return self.name

	@property
	def emote(self):
		return self.discord if self.discord else None

class Chart(models.Model):
	id = models.AutoField(primary_key=True)
	name = models.CharField(verbose_name="Chart Name", max_length=256, blank=True)
	artist = models.CharField(verbose_name="Artist", max_length=256, blank=True)
	album = models.CharField(verbose_name="Album", max_length=256, blank=True)
	charter = models.CharField(verbose_name="Charter", max_length=32, blank=True)
	tiebreaker = models.BooleanField(verbose_name="Tiebreaker", default=False)
	difficulty = models.CharField(verbose_name="Difficulty", choices=CH_DIFFICULTIES, max_length=16, default=CH_DIFFICULTIES[0][0])
	instrument = models.CharField(verbose_name="Instrument", choices=CH_INSTRUMENTS, max_length=32, default=CH_INSTRUMENTS[0][0])
	modifiers = MultiSelectField("Modifiers", choices=CH_MODIFIERS, default=CH_MODIFIERS[0][0])
	speed = models.PositiveIntegerField(verbose_name="Speed", validators=[MinValueValidator(5), MaxValueValidator(1000)], default=100)
	category = models.CharField(verbose_name="Chart Category", choices=CHART_CATEGORIES, max_length=16, default=CHART_CATEGORIES[0][0])#This needs to be choices
	brackets = models.ManyToManyField("Bracket", related_name="setlist", verbose_name="Bracket Setlist", blank=True)
	md5 = models.CharField(verbose_name="MD5 Hash", max_length=32, blank=True)
	blake3 = models.CharField(verbose_name="Blake3 Hash", max_length=32, blank=True)
	url = models.URLField(verbose_name="Chart URL", blank=True)
	icon = models.ForeignKey(CHIcon, related_name="charts", verbose_name="CH Icon", null=True, blank=True, on_delete=models.SET_NULL)
	sngfile = models.FileField(upload_to="sngfiles/", validators=[validate_chart_file], verbose_name="SNG File", null=True, blank=True)

	class Meta:
		verbose_name = "Chart"
		verbose_name_plural = "Charts"

	@property
	def long_name(self):
		return f"{self.name} - {self.charter} - {self.artist} - {self.album}{f' -{self.instrument[1]}' if self.instrument[0] != 'guitar' else ''}{f' {self.difficulty[1]}' if self.difficulty[0] != 'expert' else ''}"

	@property
	def encore_search_query(self):
		return { 'name' : self.name, 'charter' : self.charter, 'artist' : self.artist, 'album' : self.album, 'instrument': self.instrument, 'difficulty' : self.difficulty, 'blake3' : self.blake3 }

	@property
	def modifiers_short(self):
		outStr = ""
		if self.modifiers[0][1] != "NoModifiers":
			return outStr
		else:
			for mod in self.modifiers:
				outStr += f" ,{mod[0]}"
	@property
	def tournament_name(self):
		retStr = f"{self.name}"
		if self.speed != 100:
			retStr += f" ({self.speed}%)"
		if self.modifiers != ['NM']:
			retStr += self.modifiers_short
		return retStr

	def __str__(self):
		return self.name

	def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
		self.blake3 = self.blake3.upper() #Force these always upper
		self.icon = CHIcon.objects.get(name="ch_default_icon") if self.icon == None else self.icon
		self.md5 = self.md5.upper() #Steg is output as always upper
		if self.sngfile and self.sngfile.name.lower().endswith(".zip"):
			zip_file = SNGHandler(self.sngfile.open(mode='rb').read())
			self.sngfile.save(f"{zip_file.outputChartName}.sng",File(io.BytesIO(zip_file.build_sng())))
		super().save()

class Tournament(models.Model):
	id = models.AutoField(primary_key=True)
	guild = models.ForeignKey("dbot.Guilds", verbose_name="Discord Guild", db_index=True, on_delete=models.SET_NULL, null=True)
	name = models.CharField(verbose_name="Name", max_length=128, default="New Tournament")
	short_name = models.CharField(verbose_name="Short Name", max_length=16, default="NT1")
	role = models.ForeignKey("dbot.Roles", verbose_name="Participant Role", on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
	active = models.BooleanField(verbose_name="In-Progress", default=False)

	class Meta:
		verbose_name = "Tournament"
		verbose_name_plural = "Tournaments"

	def __str__(self):
		return self.name

	def active_players(self):
		return self.players.filter(active=True)

	def has_revealed_setlist(self) -> bool:
		for bracket in self.brackets.all():
			if bracket.revealed:
				return True
		return False

	def save(self):
		is_new = self.pk is None
		super().save()
		TournamentConfig.objects.get_or_create(tournament=self) if is_new else None

class TournamentConfig(models.Model):
	id = models.AutoField(primary_key=True)
	tournament = models.OneToOneField(Tournament, related_name="config", verbose_name="Tournament Configuration", on_delete=models.CASCADE)
	rules = models.TextField(verbose_name="Rules", max_length=1024, default="Some rules go here")
	ref_role = models.ForeignKey("dbot.Roles", verbose_name="Discord Ref Role", on_delete=models.SET_NULL, null=True, blank=True)
	proof_channel = models.ForeignKey("dbot.Channels", verbose_name="Discord Proof Channel", on_delete=models.SET_NULL, null=True, blank=True)#This isn't presently used
	enable_gsheets = models.BooleanField(verbose_name="Gsheets Integration", default=True)
	gsheet = models.URLField(verbose_name="Match Reporting Google Sheet", null=True, blank=True)
	version = models.CharField(verbose_name="Clone Hero Version", choices=CH_VERSIONS, max_length=32, default=CH_VERSIONS[0][0])

	class Meta:
		verbose_name = "Config"
		verbose_name_plural = "Configurations"

	def __str__(self):
		return f"{self.tournament.name} - Configuration"

class Bracket(models.Model):
	id = models.AutoField(primary_key=True)
	name = models.CharField(verbose_name="Bracket Name", max_length=128, default="New Bracket")
	tournament = models.ForeignKey(Tournament, related_name="brackets", on_delete=models.CASCADE, verbose_name="Tournament")
	score_log = models.ForeignKey("dbot.Channels", verbose_name="Score Log Channel", on_delete=models.SET_NULL, null=True, blank=True)
	is_active = models.BooleanField(verbose_name="Bracket Active", default=False)
	revealed = models.BooleanField("Setlist Revealed", default=False)
	role = models.ForeignKey("dbot.Roles", verbose_name="Bracket Role", null=True, on_delete=models.SET_NULL, blank=True, db_index=True)

	class Meta:
		verbose_name = "Bracket"

	@property
	def short_name(self):
		return self.name

	def __str__(self):
		return f"{self.tournament.short_name} - {self.name}"

	def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
		is_new = self.pk is None
		super().save()
		BracketRules.objects.create(bracket=self) if is_new or not self.ruleset else None

class BracketRules(models.Model):
	bracket = models.OneToOneField(Bracket, primary_key=True, related_name="ruleset", on_delete=models.CASCADE, verbose_name="Bracket Rules", null=False)
	num_players = models.PositiveIntegerField(verbose_name="Players", validators=[MinValueValidator(2), MaxValueValidator(4)], default=2)
	num_bans = models.IntegerField(verbose_name="Bans Per-Player", validators=[MinValueValidator(1), MaxValueValidator(4)], default=1)
	num_rounds = models.PositiveIntegerField(verbose_name="Best Of", validators=[MinValueValidator(3), MaxValueValidator(25)], default=7)
	ban_ruleset = models.CharField(verbose_name="Match Bans Ruleset", choices=BAN_RULESETS, max_length=32, default=BAN_RULESETS[0][0])
	pick_ruleset = models.CharField(verbose_name="'Who Picks' Ruleset", choices=PICK_RULESETS, max_length=32, default=PICK_RULESETS[0][0])
	tb_ruleset = models.CharField(verbose_name="Tiebreaker Ruleset", choices=TB_RULESETS, max_length=32, default=TB_RULESETS[0][0])

	class Meta:
		verbose_name = "Bracket Rules"
		verbose_name_plural = "Bracket Rules"

	@property
	def wins_needed(self):
		return int(math.ceil(self.num_rounds / 2))

	@property
	def total_bans(self) -> int:
		return self.num_bans * self.num_players

class Group(models.Model):
	id = models.AutoField(primary_key=True, db_index=True)
	name = models.CharField(verbose_name="Group Name", max_length=8, default="A")
	role = models.ForeignKey("dbot.Roles", verbose_name="Group Role", on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
	bracket = models.ForeignKey(Bracket, related_name="groups", verbose_name="Bracket", on_delete=models.CASCADE)

	class Meta:
		verbose_name = "Group"
		verbose_name_plural = "Groups"

	@property
	def tournament(self) -> Tournament:
		return self.bracket.tournament

	@property
	def active_players(self) -> list:
		return self.players.objects.filter(is_active=True)

	def __str__(self):
		return f"{self.tournament.short_name} - {self.bracket.name} - {self.name}"

class TournamentPlayer(models.Model):
	id = models.AutoField(primary_key=True)
	user = models.ForeignKey(DiscordUser, verbose_name="User", on_delete=models.SET_NULL, db_index=True, blank=True, null=True)
	name = models.CharField(verbose_name="Discord Name", max_length=128, null=True, blank=True) #This is the users tournament guild display name
	tournament = models.ForeignKey(Tournament, related_name="players", verbose_name="Tournament", on_delete=models.CASCADE)
	is_active = models.BooleanField(verbose_name="Player Active", default=False)
	#ch_name = models.CharField(verbose_name="Clone Hero Name", max_length=128, default="</Null>")
	config = SchemaField(PlayerConfig, verbose_name="Player Configuration", blank=True)

	class Meta:
		verbose_name = "Player"
		verbose_name_plural = "Players"

	def __str__(self):
		return self.ch_name

	#This needs to be checked - probably not used/not right
	@property
	def brackets(self):
		return self.tournament.brackets.objects.select_related('player').filter(players__id=self.id)

	def check_ch_name(self, name_to_find: str) -> bool:
		if not self.config or not self.config.names_list:
			return False

		return any(item.ch_name == name_to_find for item in self.config.names_list)

	@property
	def ch_name(self) -> str:
		"""
		Retrieves the primary Clone Hero name from the Pydantic config.
		"""
		if not self.config:
			return "</Null>"

		try:
			config_obj = PlayerConfig(**self.config) if isinstance(self.config, dict) else self.config
			names_list = config_obj.names_list

			if not names_list:
				return "</Null>"

			for item in names_list:
				if item.is_primary:
					return item.ch_name

			return names_list[0].ch_name

		except pydantic.ValidationError:
			return "</Null>"

	@ch_name.setter
	def ch_name(self, new_name: str):
		"""
		Sets a new primary Clone Hero name. Appends it to the list if it doesn't exist,
		and ensures all other names are no longer marked as primary.
		"""
		if not new_name:
			new_name = "</Null>"

		clean_name = new_name

		if not self.config:
			config_obj = PlayerConfig(names_list=[])
		else:
			try:
				config_obj = PlayerConfig(**self.config) if isinstance(self.config, dict) else self.config
			except pydantic.ValidationError:
				config_obj = PlayerConfig(names_list=[])

		names_list = config_obj.names_list
		name_already_exists = False

		for item in names_list:
			if item.ch_name == clean_name:
				item.is_primary = True
				name_already_exists = True
			else:
				item.is_primary = False

		if not name_already_exists:
			names_list.append(CH_Name(ch_name=clean_name, is_primary=True))

		config_obj.names_list = names_list
		self.config = config_obj


	@property
	def ch_aliases(self) -> list[str]:
		"""Returns a list of all Clone Hero names associated with this player."""
		if not self.config:
			return []
		try:
			return [item.ch_name for item in self.config.names_list]
		except pydantic.ValidationError:
			return []

class GroupSeed(models.Model):
	id = models.AutoField(primary_key=True)
	seed = models.PositiveIntegerField(blank=False, null=False)
	group = models.ForeignKey(Group, related_name="seeding", verbose_name="Group Seeding", null=True, on_delete=models.CASCADE)
	player = models.ForeignKey(TournamentPlayer, related_name="group_seeding", verbose_name="Group Seed", null=True, on_delete=models.SET_NULL)

	class Meta:
		verbose_name = "Seed Placement"
		verbose_name_plural = "Seed Placements"
		ordering = ['seed']

	def __str__(self):
		# Fallback text if there is no player assigned to this seed yet
		player_name = self.player.ch_name if self.player else "Unassigned"
		return f"{player_name} ({self.seed})"

	@property
	def seed_num(self):
		return str(self.seed)

	@property
	def player_ch_name(self):
		return self.player.ch_name if self.player else "</Null>"

	@property
	def user(self):
		return self.player.user if self.player else None

	@property
	def full_name(self):
		return f"{self.group.tournament.short_name} - {self.group.bracket.name} - Group {self.group.name} - Seed {self.seed}"

	def check_ch_name(self, testname):
		if not self.player:
			return False
		return self.player.check_ch_name(testname)

class Qualifier(models.Model):
	id = models.AutoField(primary_key=True)
	tournament = models.ForeignKey(Tournament, related_name='qualifier', verbose_name="Tournament", on_delete=models.CASCADE)
	bracket = models.ForeignKey(Bracket, related_name='qualifier', verbose_name="Bracket", blank=True, null=True, on_delete=models.CASCADE)
	charts = models.ManyToManyField(Chart, related_name="charts", verbose_name="Qualifier Chart(s)")
	limit_submissions = models.BooleanField(verbose_name="Limit Submissions to # Required", default=False)
	required_submissions = models.PositiveIntegerField(verbose_name="Required Submissions", default=1)
	form_link = models.URLField(verbose_name="Google Form Link", null=True, blank=True)
	end_time = models.DateTimeField(verbose_name="End Time", default=timezone.now)
	rules = models.TextField(verbose_name="Rules", max_length=1024, default="Placeholder rules")
	channel = models.ForeignKey("dbot.Channels", verbose_name="Submission Discord Channel", on_delete=models.SET_NULL, db_index=True, blank=True, null=True)
	gsheet = models.URLField(verbose_name="Submissions Google Sheet", null=True, blank=True)
	output = models.BooleanField(verbose_name="Msg On Submission", default=True)

	class Meta:
		verbose_name = "Qualifier"
		verbose_name_plural = "Qualifiers"

	def __str__(self):
		if self.bracket:
			return f"{self.tournament.short_name} - {self.bracket.name}"
		else:
			return f"{self.tournament.short_name}"

class QualifierSubmission(models.Model):
	id = models.CharField(primary_key=True, verbose_name="Qualifier ID", max_length=40, default=uuid.uuid1)
	player = models.ForeignKey(TournamentPlayer, related_name="qualifiers", verbose_name="Submittor", on_delete=models.CASCADE)
	submit_time = models.DateTimeField(verbose_name="Submission Time", auto_now_add=True)
	screenshot = models.ImageField(upload_to=quali_upload_dir, verbose_name="Screenshot", null=True, blank=True)
	qualifier = models.ForeignKey(Qualifier, related_name='submissions', verbose_name="Tournament Qualifier", on_delete=models.CASCADE)
	steg = SchemaField(StegScreenshot, verbose_name="Steg Data", null=True, blank=True)
	submitted = models.BooleanField(verbose_name="Uploaded to GSheet", default=False)

	class Meta:
		verbose_name = "Qualifier Submission"
		verbose_name_plural = "Qualifier Submissions"

	def __str__(self):
		return f"{self.player.ch_name} - {self.qualifier.tournament.name} {self.qualifier.bracket.name if self.qualifier.bracket else ''} Qualifier"

	@property
	def score(self):
		return self.steg.players[0].score

	def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
		if self.screenshot and not self.steg:
			from corpoch.providers import CHStegTool
			tool = CHStegTool()
			self.steg = tool.getStegInfoSync(self.screenshot)
			for i, ply in enumerate(self.steg.players):
				if not self.player.check_ch_name(ply.profile_name):
					self.steg.players.pop(i)
		super().save()

class Match(models.Model):
	id = models.CharField(primary_key=True, verbose_name="Match ID", max_length=40, default=uuid.uuid1)
	players = models.ManyToManyField(GroupSeed, related_name="match_players", verbose_name="Players", blank=True)
	loser = models.ForeignKey(TournamentPlayer, related_name="matches_lost", null=True, blank=True, on_delete=models.SET_NULL)
	winner = models.ForeignKey(TournamentPlayer, related_name="matches_won", null=True, blank=True, on_delete=models.SET_NULL)
	defer = models.BooleanField(verbose_name="Deferral Used", default=False)
	group = models.ForeignKey(Group, related_name='matches', verbose_name="Group", on_delete=models.CASCADE)#limit_options_to groups in bracket somehow?
	started_on = models.DateTimeField(verbose_name="Match Start Time", auto_now_add=True)
	ended_on = models.DateTimeField(verbose_name="Match End Time", null=True, blank=True)
	complete = models.BooleanField(verbose_name="'Complete'", default=False)
	finished = models.BooleanField(verbose_name="Finished", default=False) #Flag to match in-progress as complete, start triggers to move to completed
	submitted = models.BooleanField(verbose_name="GSheet", default=False)
	channel = models.ForeignKey("dbot.Channels", verbose_name="Ref-Tool Discord Channel", on_delete=models.SET_NULL, null=True, blank=True)
	message = models.BigIntegerField(verbose_name="Ref-Tool Discord Message ID", null=True, blank=True)
	referee = models.ForeignKey(DiscordUser, verbose_name="User", on_delete=models.SET_NULL, db_index=True, blank=True, null=True)
	exhibition = models.BooleanField(default=False)

	class Meta:
		ordering = ['-started_on']
		verbose_name = "Match"
		verbose_name_plural = "Matches"

	@property
	def ongoing(self):
		players = self.players.all()
		return self.finished == False and players.count() > 1

	@property
	def high_seed(self):
		return self.players.first()

	@property
	def low_seed(self):
		players = self.players.all()

		if players.count() > 1:
			return players[1]
		return None

	@property
	def bans(self):
		return self.match_bans.all()

	@property
	def high_seed_bans(self):
		if self.high_seed:
			return [ban for ban in self.bans if ban.player.player_id == self.high_seed.player_id]
		else:
			return []

	@property
	def low_seed_bans(self):
		if self.low_seed:
			return [ban for ban in self.bans if ban.player.player_id == self.low_seed.player_id]
		else:
			return []

	@property
	def rounds(self):
		return self.match_rounds.all()

	@property
	def tournament(self):
		return self.group.bracket.tournament

	@property
	def bracket(self):
		return self.group.bracket

	@property
	def version(self):
		self.tournament.config.version

	@property
	def score(self):
		if self.high_seed and self.low_seed:
			score1 = 0
			score2 = 0
			for round in self.rounds:
				if round.winner_id:
					if round.winner_id == self.high_seed.player_id:
						score1 += 1
					else:
						score2 += 1

			return f"{score1} - {score2}"
		else:
			return "0 - 0"

	@property
	def full_name(self):
		outStr = f"{self.tournament.short_name} - {self.bracket.name}"
		for i, ply in enumerate(self.players.iterator()):
			if i == 0:
				outStr += f" - {ply.player_ch_name}({ply.seed})"
			elif i == 1:
				outStr += f" vs {ply.player_ch_name}({ply.seed})" 
		return outStr

	@property
	def short_name(self):
		outStr = ""
		for i, ply in enumerate(self.players.iterator()):
			if i == 0:
				outStr += f"{ply.player_ch_name}({ply.seed})"
			elif i == 1:
				outStr += f" vs {ply.player_ch_name}({ply.seed})"
		return outStr

	def __str__(self):
		outStr = f"{self.tournament.short_name} - {self.bracket.name} - Group {self.group.name}"
		seeds = [seed for seed in self.players.all()]
		if len(seeds) > 1:#Not going to work 3+ players
			outStr += f" - {seeds[0].player.ch_name} ({seeds[0].seed}) vs {seeds[1].player.ch_name} ({seeds[1].seed})"
		return outStr

	def complete_match(self):
		pass

	def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
		for rnd in self.rounds:
			if rnd.screenshot and (not rnd.steg or len(rnd.steg.players) == 0):
				from corpoch.providers import CHStegTool
				tool = CHStegTool()
				rnd.steg = tool.getStegInfoSync(rnd.screenshot)
		super().save()

class MatchRound(models.Model):
	id = models.AutoField(primary_key=True)
	num = models.PositiveIntegerField(blank=False, null=False)
	match = models.ForeignKey(Match, related_name="match_rounds", verbose_name="Match ID", on_delete=models.CASCADE, null=True, blank=True)
	picked = models.ForeignKey(TournamentPlayer, related_name="picks", verbose_name="Picker", on_delete=models.CASCADE, blank=True, null=True)
	chart = models.ForeignKey(Chart, related_name="rounds_played", verbose_name="Chart Played", null=True, blank=True, on_delete=models.SET_NULL)
	winner = models.ForeignKey(TournamentPlayer, related_name="rounds_won", verbose_name="Winner", null=True, blank=True, on_delete=models.SET_NULL)
	#w_points = models.PositiveIntegerField(verbose_name="Players", validators=[MinValueValidator(1), MaxValueValidator(5)], default=1)
	loser = models.ForeignKey(TournamentPlayer, related_name="rounds_lost", verbose_name="Loser", null=True, blank=True, on_delete=models.SET_NULL)
	#l_points = models.PositiveIntegerField(verbose_name="Players", validators=[MinValueValidator(1), MaxValueValidator(5)], default=0)
	steg = SchemaField(StegScreenshot, verbose_name="Steg Data", null=True, blank=True) #This is the players list in the steg data
	screenshot = models.ImageField(upload_to=steg_upload_dir, verbose_name="Screenshot", null=True, blank=True)
	created = models.DateTimeField(verbose_name="Created Time", auto_now_add=True, null=True, blank=True)

	class Meta:
		verbose_name = "Group Match Round"
		verbose_name_plural = "Group Match Rounds"
		ordering=['num']

	def __str__(self):
		outStr = ""
		if self.picked:
			outStr += f"{self.picked} picks"
		if self.chart:
			outStr += f" {self.chart.name}"
		if self.winner:
			outStr += f" - {self.winner.ch_name} wins"
		return outStr

	def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
		if self.screenshot and not self.steg:
			from corpoch.providers import CHStegTool
			tool = CHStegTool()
			self.steg = tool.getStegInfoSync(self.screenshot)
		super().save()

#Potential class for a "Series" of tournaments - just needs to be a list of tournaments for ogranization
#class TournamentSeries(models.Model):
#	id = models.PositiveIntegerField(blank=False, null=False)

class MatchBan(models.Model):
	id = models.AutoField(primary_key=True)
	num = models.PositiveIntegerField(blank=False, null=False)
	chart = models.ForeignKey(Chart, related_name="bans", verbose_name="Chart Banned", null=True, blank=True, on_delete=models.SET_NULL)
	player = models.ForeignKey(GroupSeed, related_name="player_bans", verbose_name="Player", null=True, blank=True, on_delete=models.SET_NULL)
	match = models.ForeignKey(Match, related_name="match_bans", verbose_name="Match ID", on_delete=models.CASCADE, null=True, blank=True)
	created = models.DateTimeField(verbose_name="Created Time", auto_now_add=True, null=True, blank=True)

	class Meta:
		verbose_name = "Match Ban"
		verbose_name_plural = "Match Bans"
		ordering = ['num']

	def __str__(self):
		return str(self.chart.name)

	@property
	def get_player_ch_name(self):
		return str(self.player.ch_name)
