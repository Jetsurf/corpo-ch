import uuid, typing, json, math, io, pydantic, datetime
from itertools import chain
from requests import Session

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
from corpoch.dbot.view.helpers import build_stats_embed, build_full_stats_embed

def steg_upload_dir(self, filename):
	return f"matches/{str(self.match.group).replace(' ', '').replace(":", "")}/{self.match.id}/{uuid.uuid1()}.{filename.split('.')[-1]}"

def quali_upload_dir(self, filename):
	return f"qualifiers/{str(self.qualifier).replace(' ', '').replace(':', '')}/{self.match.id}/{uuid.uuid1()}.{filename.split('.')[-1]}"

class GSheetAPI(SingletonModel):
	api_key = EncryptedJSONField(null=False, blank=True, default=dict)
	sa_name = models.CharField(verbose_name="API Service Account Name", max_length=96)

	singleton_instance_id = 1

	def __str__(self):
		return "Google Sheets"

	class Meta:
		verbose_name = "Google Sheets API"

class DiscordUser(AbstractUser):
	"""
	Represents a Discord User. 
	"""
	objects = DiscordOAuth2Manager()
	id = models.BigIntegerField(primary_key=True, unique=True, help_text="Discord snowflake ID of user.")
	global_name = models.CharField(max_length=255, null=True, blank=True, help_text="Global or display name used on the account.")
	public_flags = models.IntegerField(null=True, blank=True, help_text="Discord account badge/flag's.")
	flags = models.IntegerField(null=True, blank=True)
	avatar = models.CharField(max_length=255, null=True, blank=True, help_text="URL of users discord avatar.")
	locale = models.CharField(max_length=255, null=True, blank=True, help_text="Users's Discord locale")
	mfa_enabled = models.BooleanField(default=False, help_text="Does user have MFA enabled for their Discord account.")
	last_login = models.DateTimeField(null=True, blank=True, help_text="User's last login time.")

	username = None
	USERNAME_FIELD = 'id'
	REQUIRED_FIELDS = ()

	def __str__(self):
		if self.global_name:
			return self.global_name
		else:
			return str(self.id)

class DiscordToken(models.Model):
	id = models.AutoField(primary_key=True, help_text="Internal ID of a token.")
	access_token = EncryptedTextField(max_length=255)
	refresh_token = EncryptedTextField(max_length=255)
	scopes = EncryptedTextField(max_length=64, default='identify guilds')
	user = models.OneToOneField(DiscordUser, null=True, on_delete=models.CASCADE, related_name="token")
	expires = models.DateTimeField(verbose_name="Expiry Time", default=timezone.now, help_text="Token expiry time.")
	#This needs an expiry date field to trigger refreshes - refresh tokens need to be handled

	class AuthError(Exception):
		def __init__(self, msg) -> None:
			super().__init__(msg)

	@property
	def __auth_header(self):
		return (settings.BOT_ID, settings.BOT_SECRET)

	@property
	def __oauth_header(self):
		return {'Authorization': f'Bearer {self.access_token}'}

	def login(self, code=None) -> None:
		self.__session = Session()
		self.__base_url = "https://discord.com/api/v10"
		self.__content_header = {'Content-Type': 'application/x-www-form-urlencoded'}
		self.__auth = { "client_id": settings.BOT_ID, "client_secret": settings.BOT_SECRET }
		if not code:
			if not self.access_token or not self.refresh_token:
				raise AuthError("Access/Refresh token not set and code is none!")
			else:
				self.__data = { "grant_type": "refresh_token", "refresh_token": self.refresh_token }
		else:
			self.__data = { "grant_type": "authorization_code",	"code": code, "redirect_uri": settings.REDIRECT_URI }
			self.__exchange_code()
	
	def __exchange_code(self):
		response = self.__session.post(f"{self.__base_url}/oauth2/token", data=self.__data, headers=self.__content_header, auth=self.__auth_header)
		if response.status_code == 200:
			self.__update(response.json())
			if self.id:
				self.save()
			return
		raise self.AuthError(f"Failed to connect to discord API {response.json()}")
	
	def update_code(self) -> str:
		if self.expires < timezone.now() + datetime.timedelta(days=2):
			self.__exchange_code()

	def __update(self, json: dict):
		self.access_token = json["access_token"]
		self.refresh_token = json["refresh_token"]
		self.scopes = json['scope']
		self.expires = timezone.now() + datetime.timedelta(seconds=json['expires_in'])

	def identity(self) -> dict:
		if not self.access_token:
			self.__exchange_code()

		response =  self.__session.get(f"{self.__base_url}/users/@me", headers=self.__oauth_header)
		if response.status_code == 200:
			return response.json()
		raise AuthError("Failed to connect to discord API")

	def guilds(self) -> list:
		if not self.access_token:
			self.__exchange_code()

		response = self.__session.get(f"{self.__base_url}/users/@me/guilds", headers=self.__oauth_header)
		if response.status_code == 200:
			return response.json()
		raise AuthError("Failed to connect to discord API")

class CHIcon(models.Model):
	"""
	Represents an Icon for a chart used in a Tournament. 
	"""
	name = models.CharField(verbose_name="Name", blank=False, max_length=32, default="newicon", primary_key=True, help_text="The icon name.")
	img = models.ImageField(upload_to="chicons/", verbose_name="Image", null=True, blank=True, help_text="URL of the chart icon.")

	class Meta:
		verbose_name = "Chart Icon"
		verbose_name_plural = "Chart Icons"

	def __str__(self):
		return self.name

	@property
	def emote(self):
		return self.discord if self.discord else None

class Chart(models.Model):
	"""
	Represents a Chart for a Bracket setlist or Qualifier. 
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID of a chart.")
	name = models.CharField(verbose_name="Chart Name", max_length=256, blank=True, help_text="Name of the chart.")
	artist = models.CharField(verbose_name="Artist", max_length=256, blank=True, help_text="Artist of the song.")
	album = models.CharField(verbose_name="Album", max_length=256, blank=True, help_text="Album the song is from.")
	charter = models.CharField(verbose_name="Charter", max_length=32, blank=True, help_text="Author of a chart.")
	boss = models.BooleanField(verbose_name="Boss Song", default=False, help_text="Is chart a 'boss' song.")
	tiebreaker = models.BooleanField(verbose_name="Tiebreaker", default=False, help_text="Is this chart a tiebreaker in a setlist.")
	difficulty = models.CharField(verbose_name="Difficulty", choices=CH_DIFFICULTIES, max_length=16, default=CH_DIFFICULTIES[0][0], help_text="Difficulty this chart is to be played on.")
	instrument = models.CharField(verbose_name="Instrument", choices=CH_INSTRUMENTS, max_length=32, default=CH_INSTRUMENTS[0][0])
	modifiers = MultiSelectField("Modifiers", choices=CH_MODIFIERS, default=CH_MODIFIERS[0][0], help_text="Modifiers expected to be used.")
	speed = models.PositiveIntegerField(verbose_name="Speed", validators=[MinValueValidator(5), MaxValueValidator(1000)], default=100, help_text="Expected playback speed.")
	category = models.CharField(verbose_name="Chart Category", choices=CHART_CATEGORIES, max_length=16, default=CHART_CATEGORIES[0][0])#This needs to be choices
	brackets = models.ManyToManyField("Bracket", related_name="setlist", verbose_name="Bracket Setlist", blank=True, help_text="Bracket setlists this chart is used in.")
	md5 = models.CharField(verbose_name="MD5 Hash", max_length=32, blank=True, help_text="The md5sum of the notes.chart/mid file. Used for steg verification.")
	blake3 = models.CharField(verbose_name="Blake3 Hash", max_length=32, blank=True, help_text="The Encore blake3 hash for a chart to import.")
	url = models.URLField(verbose_name="Chart URL", blank=True, help_text="URL this chart is available at.")
	icon = models.ForeignKey(CHIcon, related_name="charts", verbose_name="CH Icon", null=True, blank=True, on_delete=models.SET_NULL, help_text="The in-game setlist icon for the chart.")
	sngfile = models.FileField(upload_to="sngfiles/", validators=[validate_chart_file], verbose_name="SNG File", null=True, blank=True, help_text="The chart file. Stored as .sng but available as old .chart format.")

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

	@property
	def game_version(self):
		ret = self.brackets.first()
		if ret:
			return ret.tournament.config.version
		else:
			ret = self.qualifier.first()
		if ret:
			return ret.tournament.config.version
		else:
			return CH_VERSIONS[-1][0]

	def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
		self.blake3 = self.blake3.upper() #Force these always upper
		self.icon = CHIcon.objects.get(name="ch_default_icon") if self.icon == None else self.icon
		self.md5 = self.md5.upper() #Steg is output as always upper
		if self.sngfile and self.sngfile.name.lower().endswith(".zip"):
			zip_file = SNGHandler(self.sngfile.open(mode='rb').read())
			self.sngfile.save(f"{zip_file.outputChartName}.sng",File(io.BytesIO(zip_file.build_sng())))
		super().save()

class Tournament(models.Model):
	"""
	Represents a Clone Hero Tournament. 
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID of a tournament.")
	guild = models.ForeignKey("dbot.Guilds", verbose_name="Discord Guild", db_index=True, on_delete=models.SET_NULL, null=True, help_text="Discord Guild the tournament is running in.")
	name = models.CharField(verbose_name="Name", max_length=128, default="New Tournament", help_text="Full name of the tournament.")
	short_name = models.CharField(verbose_name="Short Name", max_length=16, default="NT1", help_text="Short/abbreviated name for this tournament.")
	role = models.ForeignKey("dbot.Roles", verbose_name="Participant Role", on_delete=models.SET_NULL, null=True, blank=True, db_index=True, help_text="Discord Role to assign to players in this tournament.")
	active = models.BooleanField(verbose_name="In-Progress", default=False, help_text="Is tournament active/running.")

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
	"""
	Represents a configuration for a Tournament. 
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID of a config.")
	tournament = models.OneToOneField(Tournament, related_name="config", verbose_name="Tournament Configuration", on_delete=models.CASCADE, help_text="Tournament a configuration is for.")
	rules = models.TextField(verbose_name="Rules", max_length=1024, default="Some rules go here", help_text="Rules shown to players.")
	gsheet = models.URLField(verbose_name="Match Reporting Google Sheet", null=True, blank=True, help_text="GSheet URL to post match results to.")
	version = models.CharField(verbose_name="Clone Hero Version", choices=CH_VERSIONS, max_length=32, default=CH_VERSIONS[0][0], help_text="Clone Hero verison the tournament is using.")

	class Meta:
		verbose_name = "Configuration"
		verbose_name_plural = "Configurations"

	def __str__(self):
		return f"{self.tournament.name}"

class Bracket(models.Model):
	"""
	Represents a Bracket for a Tournament. 
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID of a bracket.")
	name = models.CharField(verbose_name="Bracket Name", max_length=128, default="New Bracket", help_text="Name of the bracket")
	tournament = models.ForeignKey(Tournament, related_name="brackets", on_delete=models.CASCADE, verbose_name="Tournament", help_text="Tournament this bracket is for.")
	score_log = models.ForeignKey("dbot.Channels", verbose_name="Score Log Channel", on_delete=models.SET_NULL, null=True, blank=True)
	is_active = models.BooleanField(verbose_name="Bracket Active", default=False, help_text="Is bracket active/matches are allowed to start.")
	revealed = models.BooleanField("Setlist Revealed", default=False, help_text="Is the setlist revealed. If True, the charts for a setlist are made available.")
	role = models.ForeignKey("dbot.Roles", verbose_name="Bracket Role", null=True, on_delete=models.SET_NULL, blank=True, db_index=True, help_text="Discord role to assign to players in this bracket.")

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
	"""
	Represents a Ruleset for a Tournament Bracket. 
	"""
	bracket = models.OneToOneField(Bracket, primary_key=True, related_name="ruleset", on_delete=models.CASCADE, verbose_name="Bracket Rules", null=False, help_text="Bracket this ruleset is for.")
	num_players = models.PositiveIntegerField(verbose_name="Players", validators=[MinValueValidator(2), MaxValueValidator(4)], default=2, help_text="Number of players in a match.")
	num_bans = models.IntegerField(verbose_name="Bans Per-Player", validators=[MinValueValidator(1), MaxValueValidator(4)], default=1, help_text="Number of bans per-player in a match.")
	num_rounds = models.PositiveIntegerField(verbose_name="Best Of", validators=[MinValueValidator(3), MaxValueValidator(25)], default=7, help_text="Maximum number of rounds per-match.")
	boss_active = models.BooleanField("Boss Songs Active", default=False, help_text="Are 'Boss' songs allowed to be picked.")
	boss_bannable = models.BooleanField(verbose_name="Boss Songs Bannable", default=False, help_text="Are 'Boss' songs bannable.")
	ban_ruleset = models.CharField(verbose_name="Match Bans Ruleset", choices=BAN_RULESETS, max_length=32, default=BAN_RULESETS[0][0], help_text="Ruleset to determine how bans work.")
	pick_ruleset = models.CharField(verbose_name="'Who Picks' Ruleset", choices=PICK_RULESETS, max_length=32, default=PICK_RULESETS[0][0], help_text="Ruleset to determine who picks the next song for a round.")
	tb_ruleset = models.CharField(verbose_name="Tiebreaker Ruleset", choices=TB_RULESETS, max_length=32, default=TB_RULESETS[0][0], help_text="Ruleset to determine how tiebreakers player.")

	class Meta:
		verbose_name = "Bracket Rules"
		verbose_name_plural = "Bracket Rules"

	@property
	def wins_needed(self):
		return int(math.ceil(self.num_rounds / 2))

	@property
	def total_bans(self) -> int:
		return self.num_bans * self.num_players

	@property
	def boss_present(self):
		if len(self.bracket.setlist.filter(boss=True)) > 0:
			return True
		else:
			return False

	@property 
	def bannable_tb(self) -> bool:
		if self.tb_ruleset == TB_RULESETS[2][0]:
			return True
		else:
			return False

	@property
	def pickable_tb(self) -> bool:
		"""
		Is the tie-breaker chart pickable
		"""
		if self.tb_ruleset == TB_RULESETS[0][0] or self.tb_ruleset == TB_RULESETS[1][0]:
			return False
		else:
			return True

	def __str__(self):
		return f"{self.bracket}"

class Group(models.Model):
	"""
	Represents a Group in a Bracket for a Tournament. 
	"""
	id = models.AutoField(primary_key=True, db_index=True, help_text="The ID of the Group")
	name = models.CharField(verbose_name="Group Name", max_length=8, default="A", help_text="Group Name, full name constructed from tournament.short_name + bracket.name + group.name")
	role = models.ForeignKey("dbot.Roles", verbose_name="Group Role", on_delete=models.SET_NULL, null=True, blank=True, db_index=True, help_text="Discord role from Tournament Guild to be assigned to group members",)
	bracket = models.ForeignKey(Bracket, related_name="groups", verbose_name="Bracket", on_delete=models.CASCADE, help_text="Bracket this Group belongs to")

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
	"""
	Represents a Player (Tied to a DiscordUser) in a Tournament. 
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID of the Player")
	user = models.ForeignKey(DiscordUser, related_name="tournaments", verbose_name="User", on_delete=models.SET_NULL, db_index=True, blank=True, null=True, help_text="Discord User for Player")
	name = models.CharField(verbose_name="Guild Discord Name", max_length=128, null=True, blank=True, help_text="Display name of user in Tournament Guild")
	tournament = models.ForeignKey(Tournament, related_name="players", verbose_name="Tournament", on_delete=models.CASCADE, help_text="Tournament player signed up for.")
	is_active = models.BooleanField(verbose_name="Player Active", default=False, help_text="Is player active. False means DNF/Did not enter.")
	config = SchemaField(PlayerConfig, verbose_name="Player Configuration", blank=True, help_text="JSON Configuration feild for player")

	class Meta:
		verbose_name = "Player"
		verbose_name_plural = "Players"

	def __str__(self):
		return self.ch_name

	#This needs to be checked - probably not used/not right
	@property
	def brackets(self):
		return self.tournament.brackets.objects.select_related('player').filter(players__id=self.id)

	@property
	def ch_aliases(self) -> list[str]:
		"""Returns a list of all Clone Hero names associated with this player."""
		if not self.config:
			return []
		try:
			return [item.ch_name for item in self.config.names_list]
		except pydantic.ValidationError:
			return []

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

	@property
	def mention(self) -> str:
		"""Returns a discord formatted mention string to @ a user"""
		return f"<@{self.user.id}>"

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

	def check_ch_name(self, name_to_find: str) -> bool:
		if not self.config or not self.config.names_list:
			return False

		return any(item.ch_name == name_to_find for item in self.config.names_list)

class GroupSeed(models.Model):
	"""
	Represents a Seeding for a player in a Tournament Group. 
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID for this seed")
	seed = models.PositiveIntegerField(blank=False, null=False, help_text="Player seed within this group")
	group = models.ForeignKey(Group, related_name="seeding", verbose_name="Group Seeding", null=True, on_delete=models.CASCADE, help_text="Group this seed is for")
	player = models.ForeignKey(TournamentPlayer, related_name="group_seeding", verbose_name="Group Seed", null=True, on_delete=models.SET_NULL, help_text='Player with this seeding in the group')
	eliminated = models.BooleanField(verbose_name="Eliminated", default=False, help_text="Has player been eliminted from bracket (playoffs).")

	class Meta:
		verbose_name = "Seed Placement"
		verbose_name_plural = "Seed Placements"
		ordering = ['seed']

	def __str__(self):
		# Fallback text if there is no player assigned to this seed yet
		player_name = self.player.ch_name if self.player else "Unassigned"
		return f"{player_name} ({self.seed})"

	@property
	def full_name(self):
		return f"{self.group.tournament.short_name} - {self.group.bracket.name} - Group {self.group.name} - Seed {self.seed}"

	@property
	def mention(self) -> str:
		"""Returns a discord formatted mention string to @ a user"""
		return f"<@{self.player.user.id}>"

	@property
	def player_ch_name(self):
		return self.player.ch_name if self.player else "</Null>"

	@property
	def seed_num(self):
		"""Returns the seed placement"""
		return str(self.seed)

	@property
	def user(self):
		"""Returns the associated DiscordUser"""
		return self.player.user if self.player else None

	def check_ch_name(self, testname):
		if not self.player:
			return False
		return self.player.check_ch_name(testname)

class Qualifier(models.Model):
	"""
	Represents a Seeding for a player in a Tournament Group. 
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID of this Qualifier")
	tournament = models.ForeignKey(Tournament, related_name='qualifier', verbose_name="Tournament", on_delete=models.CASCADE, help_text="Tournament this qualifer is for.")
	bracket = models.ForeignKey(Bracket, related_name='qualifier', verbose_name="Bracket", blank=True, null=True, on_delete=models.CASCADE, help_text="Specific bracket in a tournament this qualifier is for.")
	charts = models.ManyToManyField(Chart, related_name="qualifier", verbose_name="Qualifier Chart(s)", help_text="Chart(s) that this qualifier uses.")
	limit_submissions = models.BooleanField(verbose_name="Limit Submissions to # Required", default=False, help_text="Limit players to single qualifier submission.")
	required_submissions = models.PositiveIntegerField(verbose_name="Required Submissions", default=1, help_text="If limit_submissions=False, the number of submissions required for a player to qualify.")
	form_link = models.URLField(verbose_name="Google Form Link", null=True, blank=True, help_text="Google Form link to show players while submitting their qualifier.")
	end_time = models.DateTimeField(verbose_name="End Time", default=timezone.now, help_text="UTC Time this qualifier ends. +2 hours from this time, the results are allowed in the API.")
	rules = models.TextField(verbose_name="Rules", max_length=1024, default="Placeholder rules", help_text="Rules shown to players for this qualifier.")
	channel = models.ForeignKey("dbot.Channels", verbose_name="Submission Discord Channel", on_delete=models.SET_NULL, db_index=True, blank=True, null=True, help_text="Discord Channel users will submit scores in.")
	gsheet = models.URLField(verbose_name="Submissions Google Sheet", null=True, blank=True, help_text="Google Sheet to submit qualifier scores to.")
	output = models.BooleanField(verbose_name="Msg On Submission", default=True, help_text="Publically post in discord when user submits a qualifier.")

	class Meta:
		verbose_name = "Qualifier"
		verbose_name_plural = "Qualifiers"

	def __str__(self):
		if self.bracket:
			return f"{self.tournament.short_name} - {self.bracket.name}"
		else:
			return f"{self.tournament.short_name}"

class QualifierSubmission(models.Model):
	"""
	Represents a Submission for a qualifier for a Tournament or Bracket. 
	"""
	id = models.CharField(primary_key=True, verbose_name="Qualifier ID", max_length=40, default=uuid.uuid1, help_text="UUID of the submission.")
	player = models.ForeignKey(TournamentPlayer, related_name="qualifiers", verbose_name="Submittor", on_delete=models.CASCADE, help_text="The Player that submitted a qualifier.")
	submit_time = models.DateTimeField(verbose_name="Submission Time", auto_now_add=True, help_text="Submission timestamp.")
	screenshot = models.ImageField(upload_to=quali_upload_dir, verbose_name="Screenshot", null=True, blank=True, help_text="The screenshot for a submission.")
	qualifier = models.ForeignKey(Qualifier, related_name='submissions', verbose_name="Tournament Qualifier", on_delete=models.CASCADE, help_text="Qualifier that a submission was sent for.")
	steg = SchemaField(StegScreenshot, verbose_name="Steg Data", null=True, blank=True, help_text="Clone Hero screenshot steg data.")
	submitted = models.BooleanField(verbose_name="Uploaded to GSheet", default=False, help_text="Is submission sent to associated GSheet.")

	class Meta:
		verbose_name = "Qualifier Submission"
		verbose_name_plural = "Qualifier Submissions"

	def __str__(self):
		return f"{self.player.ch_name} - {self.qualifier.tournament.name} {self.qualifier.bracket.name if self.qualifier.bracket else ''} Qualifier"

	@property
	def score(self):
		return self.steg.players[0].score

	@property
	def display_profile_name(self) -> str:
		"""
		Always returns the current primary ch_name of the player, 
		acting as a dynamic reference.
		"""
		return self.player.ch_name

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
	"""
	Represents a Match played for a Tournament. 
	"""
	id = models.CharField(primary_key=True, verbose_name="Match ID", max_length=40, default=uuid.uuid1, help_text="UUID for a match.")
	players = models.ManyToManyField(GroupSeed, related_name="match_players", verbose_name="Players", blank=True, help_text="Players that participated in a match.")
	loser = models.ForeignKey(TournamentPlayer, related_name="matches_lost", null=True, blank=True, on_delete=models.SET_NULL, help_text="Player that lost the match.")
	winner = models.ForeignKey(TournamentPlayer, related_name="matches_won", null=True, blank=True, on_delete=models.SET_NULL, help_text="Player that won the match.")
	defer = models.BooleanField(verbose_name="Deferral Used", default=False, help_text="Was a deferral used.")
	group = models.ForeignKey(Group, related_name='matches', verbose_name="Group", on_delete=models.CASCADE, help_text="Group the match was played for.")
	started_on = models.DateTimeField(verbose_name="Match Start Time", auto_now_add=True, help_text="Match start time.")
	ended_on = models.DateTimeField(verbose_name="Match End Time", null=True, blank=True, help_text="Match end time.")
	complete = models.BooleanField(verbose_name="'Complete'", default=False, help_text="Match is finalized, but waiting for screenshots.")
	finished = models.BooleanField(verbose_name="Finished", default=False, help_text="Match is finished and has all screenshots/data.")
	submitted = models.BooleanField(verbose_name="GSheet", default=False, help_text="Match is uploaded to GSheet for Tournament.")
	channel = models.ForeignKey("dbot.Channels", verbose_name="Ref-Tool Discord Channel", on_delete=models.SET_NULL, null=True, blank=True, help_text="Discord Channel the reftool was ran in for a match.")
	message = models.BigIntegerField(verbose_name="Ref-Tool Discord Message ID", null=True, blank=True, help_text="Discord snowflake ID of the message for a match.")
	referee = models.ForeignKey(DiscordUser, related_name="matches_reffed", verbose_name="Referee", on_delete=models.SET_NULL, db_index=True, blank=True, null=True, help_text="Discord User for the refree of a match.")
	exhibition = models.BooleanField(default=False, help_text="Is a match an exhibition match (not an official match).")

	class Meta:
		ordering = ['-started_on']
		verbose_name = "Match"
		verbose_name_plural = "Matches"

	@property
	def ongoing(self):
		players = self.players.all()
		return self.complete == False and players.count() > 1

	@property
	def high_seed(self):
		return self.players.first()

	@property
	def low_seed(self):
		players = self.players.all()

		if players.count() > 1:
			return players[1]
		return None

	#Bans/Rounds are shorthands for all Ban/Match objects
	@property
	def bans(self):
		return self.match_bans.select_related().all()

	@property
	def rounds(self):
		return self.match_rounds.select_related().all()

	@property
	def current_round(self):
		if self.rounds.count() != 0:
			return self.rounds.latest()
		else:
			return None

	@property
	def previous_round(self):
		if self.rounds.count() > 1:
			return self.rounds.all().order_by('-num')[1]
		else:
			return None

	@property
	def high_seed_bans(self):
		if self.high_seed:
			return [ban for ban in self.bans if ban.player.id == self.high_seed.player_id]
		else:
			return []

	@property
	def low_seed_bans(self):
		if self.low_seed:
			return [ban for ban in self.bans if ban.player.id == self.low_seed.player_id]
		else:
			return []

	@property
	def rounds(self):
		return self.match_rounds.all()

	@property
	def ruleset(self):
		return self.group.bracket.ruleset

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
	def high_seed_score(self):
		if self.high_seed and self.low_seed:
			score = 0
			for round in self.rounds:
				if round.winner_id and round.winner_id == self.high_seed.player_id:
					score += 1
			return score
		else:
			return 0
		
	@property
	def low_seed_score(self):
		if self.high_seed and self.low_seed:
			score = 0
			for round in self.rounds:
				if round.winner_id and round.winner_id == self.low_seed.player_id:
					score += 1
			return score
		else:
			return 0

	def get_score(self, asint=False):
		if self.high_seed and self.low_seed:
			score1 = 0
			score2 = 0
			for round in self.rounds:
				if round.winner_id:
					if round.winner_id == self.high_seed.player_id:
						score1 += 1
					else:
						score2 += 1

			if asint:
				return [score1, score2]
			else:
				return f"{score1} - {score2}"
		else:
			if asint:
				return [0, 0]
			else:
				return "0 - 0"

	@property
	def score(self):
		return self.get_score()

	@property
	def score_int(self):
		return self.get_score(asint=True)

	@property
	def tiebreaker(self) -> bool:
		#Is match currently in tiebreaker state, is not if match played TB
		if self.score_int[0] == self.ruleset.wins_needed - 1 and self.score_int[1] == self.ruleset.wins_needed - 1:
			return True
		else:
			return False

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

	@property
	def picking_player(self):
		if self.rounds.count() == 0 and self.bans.count() != self.ruleset.total_bans:
			if self.bans.count() % self.ruleset.num_players == 0:
				if self.defer:
					picked = self.low_seed.player
				else:
					picked = self.high_seed.player
			else:
				if self.defer:
					picked = self.high_seed.player
				else:
					picked = self.low_seed.player
		elif self.tiebreaker and self.ruleset.tb_ruleset == 'refdecide':
			picked = None
		elif self.tiebreaker and self.ruleset.tb_ruleset == 'csc':
			picked = None
		elif self.tiebreaker and self.ruleset.tb_ruleset == 'banpick':
			if self.bans.count() > self.ruleset.total_bans:
				picked = self.previous_round.loser
			else:
				picked = self.current_round.winner
		elif self.ruleset.pick_ruleset == "loserpicks":
			if self.rounds.count() == 1:
				if self.defer:
					picked = self.low_seed.player
				else:
					picked = self.high_seed.player
			else:
				picked = self.previous_round.loser
		else: #Alternate pick
			if self.rounds.count() == 1:
				if self.defer:
					prevPicked = self.low_seed.player
				else:
					prevPicked = self.high_seed.player
			else:
				prevPicked = self.previous_round.picked 
			if self.high_seed.player == prevPicked:
				picked = self.high_seed.player
			else:
				picked = self.low_seed.player
		return picked

	@property
	def setlist(self):
		if self.group:
			return self.group.bracket.setlist
		else:
			return None

	@property
	def setlist_remaining(self):
		bans = self.bans.values_list('chart', flat=True)
		rounds = self.rounds.values_list('chart', flat=True)
		if self.tiebreaker:
			if self.ruleset.tb_ruleset == 'refdecide':
				charts = self.setlist.select_related('icon').exclude(pk__in=list(chain(bans, rounds)))
			elif self.ruleset.tb_ruleset == "banpick":
				charts = self.setlist.select_related('icon').filter(tiebreaker=True).exclude(pk__in=bans)
			else:
				charts = self.setlist.select_related('icon').filter(tiebreaker=True)
		else:
			if self.ruleset.boss_present and not self.ruleset.boss_active:
				charts = self.setlist.select_related('icon').filter(tiebreaker=False, boss=False).exclude(pk__in=list(chain(bans, rounds)))
			else:
				charts = self.setlist.select_related('icon').filter(tiebreaker=False).exclude(pk__in=list(chain(bans, rounds)))
		return charts

	def add_ban(self, player: TournamentPlayer, chart: Chart):
		newBan = MatchBan(num=len(self.bans), player=player, chart=chart, match=self)
		newBan.save()
		if self.bans.count() == self.ruleset.total_bans or self.tiebreaker:
			self.add_round()

	def add_round(self):
		chart = None
		if len(self.rounds) == 0:
			if self.defer and self.ruleset.ban_ruleset == "deferboth":
				picked = self.low_seed.player
			else:
				picked = self.high_seed.player
		elif self.tiebreaker and self.ruleset.tb_ruleset == 'refdecide':
			picked = None
		elif self.tiebreaker and self.ruleset.tb_ruleset == 'csc':
			fret, strum = 0, 0
			for rnd in self.rounds:
				if rnd.chart.category == "fret":
					fret += 1
				elif rnd.chart.category == "strum":
					strum += 1

			picked = None
			if strum < fret:
				chart = Chart.objects.get(category=CHART_CATEGORIES[3][0], tiebreaker=True, brackets=self.bracket)
			elif fret < strum:
				chart = Chart.objects.get(category=CHART_CATEGORIES[2][0], tiebreaker=True, brackets=self.bracket)
			else:
				chart = Chart.objects.get(category=CHART_CATEGORIES[1][0], tiebreaker=True, brackets=self.bracket)
		elif self.tiebreaker and self.ruleset.tb_ruleset == 'banpick':
			picked = self.current_round.loser
		elif self.ruleset.pick_ruleset == "loserpicks":
			picked = self.current_round.loser
		else:
			prevPicked = self.current_round.loser
			if self.high_seed.player == prevPicked:
				picked = self.high_seed.player
			else:
				picked = self.low_seed.player

		if len(self.rounds) > 0:
			self.current_round.save()
		if not self.finished:
			rnd = MatchRound(num=len(self.rounds) + 1, match=self, picked=picked, chart=chart)
			rnd.save()

	def remove_round(self):
		rnd = self.rounds[-1]
		if rnd.id:
			rnd.delete()

	def remove_ban(self):
		ban = self.bans.pop()
		if ban.id:
			ban.delete()

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
	"""
	Represents a round of a Match played for a Tournament. 
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID for a round.")
	num = models.PositiveIntegerField(blank=False, null=False, help_text="Round number of a specific match.")
	match = models.ForeignKey(Match, related_name="match_rounds", verbose_name="Match ID", on_delete=models.CASCADE, null=True, blank=True, help_text="Match the round was played for.")
	picked = models.ForeignKey(TournamentPlayer, related_name="picks", verbose_name="Picker", on_delete=models.CASCADE, blank=True, null=True, help_text="Player that picked the chart played.")
	chart = models.ForeignKey(Chart, related_name="rounds_played", verbose_name="Chart Played", null=True, blank=True, on_delete=models.SET_NULL, help_text="Chart that was played.")
	winner = models.ForeignKey(TournamentPlayer, related_name="rounds_won", verbose_name="Winner", null=True, blank=True, on_delete=models.SET_NULL, help_text="Winner of a round.")
	#w_points = models.PositiveIntegerField(verbose_name="Players", validators=[MinValueValidator(1), MaxValueValidator(5)], default=1)
	loser = models.ForeignKey(TournamentPlayer, related_name="rounds_lost", verbose_name="Loser", null=True, blank=True, on_delete=models.SET_NULL, help_text="Loser of a round.")
	#l_points = models.PositiveIntegerField(verbose_name="Players", validators=[MinValueValidator(1), MaxValueValidator(5)], default=0)
	steg = SchemaField(StegScreenshot, verbose_name="Steg Data", null=True, blank=True, help_text="Clone Hero screenshot steg data.")
	screenshot = models.ImageField(upload_to=steg_upload_dir, verbose_name="Screenshot", null=True, blank=True, help_text="Screenshot for a match.")
	created = models.DateTimeField(verbose_name="Created Time", auto_now_add=True, null=True, blank=True, help_text="Timestamp the round was started.")

	class Meta:
		verbose_name = "Group Match Round"
		verbose_name_plural = "Group Match Rounds"
		ordering = ['num']
		get_latest_by = 'num'

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

	#TODO: Move picked/etc logic to here

	@property
	def is_tiebreaker(self) -> bool:
		if self.num == self.match.bracket.ruleset.num_rounds:
			return True
		else:
			return False

	@property
	def steg_embed(self):
		embed = build_stats_embed(self.steg, f"Match {self.match} - Round {self.num} Results")
		embed.set_thumbnail(url=f"https://{settings.BASE_URL}{self.screenshot.url}")
		embed.set_footer(text=embed.footer.text, icon_url = f"https://{settings.BASE_URL}{self.chart.icon.img.url}")
		return embed

	@property
	def full_steg_embed(self):
		embed = build_full_stats_embed(self.steg, f"Match {self.match} - Round {self.num} FULL Results")
		embed.set_thumbnail(url=f"https://{settings.BASE_URL}{self.screenshot.url}")
		embed.set_footer(text=embed.footer.text, icon_url = f"https://{settings.BASE_URL}{self.chart.icon.img.url}")
		return embed

#Potential class for a "Series" of tournaments - just needs to be a list of tournaments for ogranization
#class TournamentSeries(models.Model):
#	id = models.PositiveIntegerField(blank=False, null=False)

class MatchBan(models.Model):
	"""
	Represents a player ban for a Match played in a Tournament. 
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID for a ban.")
	num = models.PositiveIntegerField(blank=False, null=False, help_text="Order in which a ban was picked.")
	chart = models.ForeignKey(Chart, related_name="bans", verbose_name="Chart Banned", null=True, blank=True, on_delete=models.SET_NULL, help_text="The chart that was banned.")
	player = models.ForeignKey(TournamentPlayer, related_name="player_bans", verbose_name="Player", null=True, blank=True, on_delete=models.SET_NULL, help_text="Player that chose a ban.")
	match = models.ForeignKey(Match, related_name="match_bans", verbose_name="Match ID", on_delete=models.CASCADE, null=True, blank=True, help_text="Match a ban was made for.")
	created = models.DateTimeField(verbose_name="Created Time", auto_now_add=True, null=True, blank=True, help_text="Timestamp a ban was chosen.")

	class Meta:
		verbose_name = "Match Ban"
		verbose_name_plural = "Match Bans"
		ordering = ['num']
		get_latest_by = 'num'

	def __str__(self):
		return str(self.chart.name)

	@property
	def get_player_ch_name(self):
		return str(self.player.ch_name)
