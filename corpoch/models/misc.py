import datetime, json
from requests import Session

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

from encrypted_fields.fields import EncryptedJSONField, EncryptedTextField
from solo.models import SingletonModel

from corpoch import settings
from corpoch.managers import DiscordOAuth2Manager

from .match import Match, TournamentPlayer

class GSheetAPI(SingletonModel):
	api_key = EncryptedJSONField(null=False, blank=True, default=dict)
	singleton_instance_id = 1

	class Meta:
		verbose_name = "Google Sheets API"
		app_label = 'corpoch'

	def __str__(self):
		return "Google Sheets"

	def name(self):
		if self.api_key:
			return self.api_key.get('client_email')
		else:
			return "None"

	name.short_description = "Service Account Name"
	sa_name = property(name)

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
	banner = models.CharField(max_length=255, null=True, blank=True, help_text="URL of users discord banner.")
	accent_color = models.PositiveIntegerField(null=True, blank=True, help_text="Users banner accent color")
	locale = models.CharField(max_length=255, null=True, blank=True, help_text="Users's Discord locale")
	mfa_enabled = models.BooleanField(default=False, help_text="Does user have MFA enabled for their Discord account.")
	last_login = models.DateTimeField(null=True, blank=True, help_text="User's last login time.")

	username = None
	USERNAME_FIELD = 'id'
	REQUIRED_FIELDS = ()

	class Meta:
		verbose_name = "Discord User"
		verbose_name_plural = "Discord Users"
		app_label = 'corpoch'

	def __str__(self):
		if self.global_name:
			return self.global_name
		else:
			return str(self.id)

	@property
	def career_stats(self):
		"""
		Used for Django View. Can likely be retooled for easier access/use
		"""
		user = self
		matches =  Match.objects.filter(players__player__user=user).order_by('-started_on')
		rounds = []
		stats = {
			'match_wins' : 0,
			'match_loss' : 0,
			'song_wins' : 0,
			'song_loss' : 0,
			'notes_hit' : 0,
			'notes_total' : 0,
			'ghosts' : 0,
			'phrases_hit' : 0,
			'phrases_total' : 0,
			'score' : 0,
			'fcs' : 0,
			'streak' : { 'song' : "temp", "notes" : 0, "screenshot" : "temp" },
			'matches_reffed' : Match.objects.filter(referee=user).count()
		}
		for match in matches:
			if match.winner and match.winner.user == user:
				stats['match_wins'] += 1
			elif match.loser and match.loser.user == user:
				stats['match_loss'] += 1

			if match.high_seed.player.user == user:
				player = match.high_seed.player
			else:
				player = match.low_seed.player

			for round in match.rounds.reverse():
				if round.winner and player == round.winner:
					stats['song_wins'] += 1
				elif round.loser and player == round.loser:
					stats['song_loss'] += 1

				if len(round.steg.players) > 0:
					if player.check_ch_name(round.steg.players[0].profile_name):
						ply_steg = round.steg.players[0]
						opponent_steg = round.steg.players[1]
					else:
						ply_steg = round.steg.players[1]
						opponent_steg = round.steg.players[0]

					# Used for returning back to view for round stats, extracts non-model-field round info
					score_diff = ply_steg.score - opponent_steg.score
					ret_round = {
						"data" : round,
						"score" : f"{ply_steg.score:,}",
						"score_diff" : f"{"+" if score_diff > 0 else ""}{score_diff:,}"
					}

					stats['notes_total'] += ply_steg.total_notes
					stats['notes_hit'] += ply_steg.notes_hit
					stats['ghosts'] += ply_steg.frets_ghosted
					stats['phrases_hit'] += ply_steg.sp_phrases_earned
					stats['phrases_total'] += ply_steg.sp_phrases_total
					stats['score'] += ply_steg.score
					if ply_steg.is_fc:
						stats['fcs'] += 1
					if stats['streak']['notes'] < ply_steg.max_streak:
						stats['streak']['song'] = round.chart.tournament_name
						stats['streak']['notes'] = ply_steg.max_streak
						stats['streak']['screenshot'] = round.screenshot_full_url
				rounds.append(ret_round)

		stats['score'] = f"{stats['score']:,}"
		if stats['match_wins'] + stats['match_loss'] > 0:
			stats['match_percent'] = f"{(stats['match_wins'] / (stats['match_wins'] + stats['match_loss']) * 100):.2f}%"
		else:
			stats['match_percent'] = "0.0%"

		if stats['song_wins'] + stats['song_loss'] > 0:
			stats['song_percent'] = f"{(stats['song_wins'] / (stats['song_wins'] + stats['song_loss']) * 100):.2f}%"
		else:
			stats['song_percent'] = "0.0%"

		if stats['notes_total'] > 0:
			stats['notes_percent'] = f"{(stats['notes_hit'] / stats['notes_total'] * 100):.2f}%"
		else:
			stats['notes_percent'] = "0.0%"

		if stats['phrases_total'] > 0:
			stats['phrases_percent'] = f"{stats['phrases_hit'] / stats['phrases_total'] * 100:.2f}%"
		else:
			stats['phrases_percent'] = "0.0%"

		stats['phrases_hit'] = f"{stats['phrases_hit']:,}"
		stats['phrases_total'] = f"{stats['phrases_total']:,}"
		stats['songs_total'] = stats['song_wins'] + stats['song_loss']
		if stats['songs_total'] > 0:
			stats['miss_average'] = f"{(stats['notes_total'] - stats['notes_hit']) / stats['songs_total']:.1f}"
			stats['ghosts_average'] = f"{stats['ghosts'] / stats['songs_total']:.1f}"
		else:
			stats['miss_average'] = "0.0"
			stats['ghosts_average'] = "0.0"

		stats['notes_hit'] = f"{stats['notes_hit']:,}"
		stats['notes_total'] = f"{stats['notes_total']:,}"
		stats['streak']['notes'] = f"{stats['streak']['notes']:,}"
		stats['rounds'] = rounds

		stats["ch_names"] = []
		for player in TournamentPlayer.objects.filter(user=user):
			for name in player.ch_aliases:
				stats['ch_names'].append(name)

		return stats

class DiscordToken(models.Model):
	"""
	Set of Discord OAuth credentials for a user. Has helper functions to perform actions as the user
	"""
	id = models.AutoField(primary_key=True, help_text="Internal ID of a token.")
	access_token = EncryptedTextField(max_length=255)
	refresh_token = EncryptedTextField(max_length=255)
	scopes = EncryptedTextField(max_length=64, default='identify guilds guilds.join')
	user = models.OneToOneField(DiscordUser, null=True, on_delete=models.CASCADE, related_name="token")
	expires = models.DateTimeField(verbose_name="Expiry Time", default=timezone.now, help_text="Token expiry time.")

	class Meta:
		verbose_name = "Discord Token"
		verbose_name_plural = "Discord Tokens"
		app_label = 'corpoch'

	class AuthError(Exception):
		def __init__(self, msg) -> None:
			super().__init__(msg)

	@property
	def __auth_header(self):
		"""
		Used with Discord API calls to generate OAuth2 Credentials for the bot
		"""
		return (settings.BOT_ID, settings.BOT_SECRET)

	@property
	def __bot_auth(self):
		"""
		Used for Discord API calls as the bot on behalf of the user (ie with guild joins/invites)
		"""
		return { 'Content-Type' : 'application/json', 'Authorization' : f'Bot {settings.BOT_TOKEN}'}

	@property
	def __oauth_header(self):
		"""
		Used for Discord API calls to retreive information as used (IE identify, no bot perms needed)
		"""
		return {'Authorization': f'Bearer {self.access_token}'}

	def login(self, code=None) -> None:
		self.__session = Session()
		self.__base_url = "https://discord.com/api/v10"
		self.__content_header = {'Content-Type': 'application/x-www-form-urlencoded'}
		self.__guilds = None
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
		if self.user:
			self.save()

	def identity(self) -> dict:
		if not self.access_token:
			self.__exchange_code()

		response =  self.__session.get(f"{self.__base_url}/users/@me", headers=self.__oauth_header)
		if response.status_code == 200:
			return response.json()
		raise AuthError("Failed to connect to discord API")

	def guilds(self) -> list:
		if not hasattr(self, '__session'):
			self.login()
		if not self.access_token:
			self.__exchange_code()

		response = self.__session.get(f"{self.__base_url}/users/@me/guilds", headers=self.__oauth_header)
		if response.status_code == 200:
			self.__guilds = response.json()
			return response.json()
		raise AuthError("Failed to connect to discord API")

	def invite_to_guild(self, guild):
		if not hasattr(self, '__session'):
			self.login()
		if "guilds.join" in self.scopes:
			response = self.__session.put(f"{self.__base_url}/guilds/{guild.id}/members/{self.user.id}", headers=self.__bot_auth, data=json.dumps({ "access_token" : str(self.access_token) }))

			if response.status_code == 201:
				return True
			elif response.status_code == 204:
				# User already a member
				return False
			else:
				raise self.AuthError(f"OAuth guild join error {response.status_code} joining user {self.user.id} to guild {guild.id}\n{response.text}")
		else:
			raise self.AuthError("User OAuth scopes do not include guilds.join")
