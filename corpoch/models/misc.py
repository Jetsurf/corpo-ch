import binascii, datetime, io, json, numpy, requests, scipy, struct, traceback

from PIL import Image, ImageDraw, ImageFont
from requests import Session

from django.core.files import File
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

from encrypted_fields.fields import EncryptedJSONField, EncryptedTextField
from solo.models import SingletonModel

from corpoch import settings
from corpoch.managers import DiscordOAuth2Manager

from .match import Match, TournamentPlayer

def avatar_upload_dir(self, filename):
	#Discord prepended to file tells bot to update if changed from discord
	if "discord" in filename:
		new_name = self.discord_avatar.split("/")[5].split(".")[0]
	else:
		new_name = str(self.id)
	return f"profile/avatars/{new_name}.{filename.split('.')[-1]}"

def banner_upload_dir(self, filename):
	if "discord" in filename:
		new_name = self.discord_banner.split("/")[5].split(".")[0]
	elif "accent" in filename:
		new_name = str(self.accent_color)
	else:
		new_name = str(self.id)
	return f"profile/banners/{new_name}.{filename.split('.')[-1]}"

def tag_upload_dir(self, filename):
	return f"profile/tags/{self.id}/{self.tag_hash}.{filename.split('.')[-1]}"

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

class DiscordTag(models.Model):
	id = models.BigIntegerField(primary_key=True, unique=True, help_text="Discord snowflake ID of the guild.")
	badge = models.CharField(max_length=255, null=True, blank=True, help_text="URL of users discord banner img.")
	tag = models.CharField(max_length=8, null=True, blank=True, help_text="Text for users discord banner img.")
	tag_image = models.ImageField(upload_to=tag_upload_dir, verbose_name="Tag Image", null=True, blank=True, help_text="Avatar image for user.")

	def __str__(self):
		return self.tag

	@property
	def tag_hash(self):
		return self.badge.split("/")[5].split(".")[0]

	@property
	def image(self):
		if not self.tag_image:
			font = ImageFont.truetype('OpenSans-Bold.ttf', size = 20)
			box = font.getbbox(self.tag)
			print(f"Font box: {box}")
			width = 36 + font.getbbox(self.tag)[2]
			print(f"Font width: {width}")
			#font = ImageFont.truetype(f'{settings.PROJECT_HOME}/corpoch/static/mainapp/fontawesome-free-5.15.3-web/webfonts/fa-regular-400.ttf', size=2)
			image = Image.new("RGBA", (width, 32), f"#22242A")
			response = requests.get(self.badge, data=None, headers={'User-Agent': "corpoch"}, stream=True)
			badge_img = Image.open(io.BytesIO(response.content))
			badge_img = badge_img.convert("RGBA")
			badge_img = badge_img.resize((24, 24))
			image.paste(badge_img, (4, 4, 28, 28), badge_img)
			draw = ImageDraw.Draw(image)
			draw.text((32, 0), text=self.tag, fill=(255, 255, 255), font=font)

			buf = io.BytesIO()
			image.save(buf, format="PNG")
			img = File(buf, "tag.png")
			self.tag_image = img
			self.save()

		return self.tag_image.url

class DiscordUser(AbstractUser):
	"""
	Represents a Discord User. 
	"""
	objects = DiscordOAuth2Manager()
	id = models.BigIntegerField(primary_key=True, unique=True, help_text="Discord snowflake ID of user.")
	global_name = models.CharField(max_length=255, null=True, blank=True, help_text="Global or display name used on the account.")
	public_flags = models.IntegerField(null=True, blank=True, help_text="Discord account badge/flag's.")
	flags = models.IntegerField(null=True, blank=True)
	discord_avatar = models.CharField(max_length=255, null=True, blank=True, help_text="URL of users discord avatar.")
	avatar = models.ImageField(upload_to=avatar_upload_dir, verbose_name="Avatar Image", null=True, blank=True, help_text="Avatar image for user.")
	discord_banner = models.CharField(max_length=255, null=True, blank=True, help_text="URL of users discord banner.")
	banner = models.ImageField(upload_to=banner_upload_dir, verbose_name="Banner Image", null=True, blank=True, help_text="Banner image for user.")
	tag = models.ForeignKey(DiscordTag, null=True, verbose_name="Discord Tag", on_delete=models.SET_NULL)
	accent_color = models.PositiveIntegerField(null=True, blank=True, help_text="Users banner accent color")
	locale = models.CharField(max_length=255, null=True, blank=True, help_text="Users's Discord locale")
	mfa_enabled = models.BooleanField(default=False, help_text="Does user have MFA enabled for their Discord account.")
	last_login = models.DateTimeField(null=True, blank=True, help_text="User's last login time.")


	username = None
	__accent_color = None #Private check for incoming accent_color == None from discord
	primary_guild = None
	USERNAME_FIELD = 'id'
	REQUIRED_FIELDS = ()

	class Meta:
		verbose_name = "Discord User"
		verbose_name_plural = "Discord Users"
		app_label = 'corpoch'

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.__accent_color = self.accent_color
		if self.tag:
			self.primary_guild = self.tag.id

	def __str__(self):
		if self.global_name:
			return self.global_name
		else:
			return str(self.id)

	def get_short_name(self):
		return self.global_name

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
		for player in TournamentPlayer.objects.filter(user=user).order_by("-id"):
			for name in player.ch_aliases:
				if not name in stats['ch_names']:
					stats['ch_names'].append(name)

		return stats

	@property
	def avatar_dominate_color(self):
		image = Image.open(self.avatar)
		#Find dominate color in avatar
		array = numpy.asarray(image)
		shape = array.shape
		try:
			array = array.reshape(numpy.prod(shape[:2]), shape[2]).astype(float)
		except:
			return int("0xababab", 16)

		codes, dist = scipy.cluster.vq.kmeans(array, 2)
		vectors, dist = scipy.cluster.vq.vq(array, codes)
		counts, bins = numpy.histogram(vectors, len(codes))
		index_max = numpy.argmax(counts)
		peak = codes[index_max]
		color = binascii.hexlify(bytearray(int(c) for c in peak)).decode('ascii')
		return int(f"0x{color}", 16)

	@property
	def discord_avatar_hash(self):
		return self.discord_avatar.split("/")[5].split(".")[0]

	@property
	def discord_banner_hash(self):
		return self.discord_banner.split("/")[5].split(".")[0]

	def save(self, *args, **kwargs):

		if not self.discord_avatar:
			return # Break early as user object is only partial

		#This function uses the internal __accent_color as a check to prevent discord users leaving it auto-set, forcing none here

		#User changed/set discord accent color, set now before updates
		if self.accent_color != None and self.accent_color != self.__accent_color:
			self.__accent_color = self.accent_color

		try:
			#Update avatar if discord hash updated, and not manually uploaded
			if self.avatar == None or str(self.id) not in self.avatar.name:
				if self.avatar and self.discord_avatar_hash not in self.avatar.name and str(self.id) not in self.avatar.name:
					pass
				elif not self.avatar or not self.discord_avatar_hash in self.avatar.name:
					print(f"Updating {self.id} avatar {self.discord_avatar}")
					response = requests.get(self.discord_avatar, data=None, headers={'User-Agent': "corpoch"}, stream=True)
					self.avatar = File(io.BytesIO(response.content), "discord.png")

				if not self.accent_color:
					self.__accent_color = self.avatar_dominate_color

			#Update banner if discord hash updated, and not manually uploaded
			if self.banner == None or str(self.id) not in self.banner.name:
				if not self.__accent_color:
					self.__accent_color = self.avatar_dominate_color
					self.accent_color = self.__accent_color
				if self.discord_banner:
					if not self.banner or not self.discord_banner_hash in self.banner.name:
						print(f"Updating {self.id} banner {self.discord_banner}")
						response = requests.get(self.discord_banner, data=None, headers={'User-Agent': "corpoch"}, stream=True)
						self.banner = File(io.BytesIO(response.content), "discord.png")
					else:
						pass #Don't trigger below
				elif self.banner == None or str(self.__accent_color) not in self.banner.name:
					generated = DiscordUser.objects.filter(banner__contains=self.__accent_color)
					if generated.count() > 0:
						img = generated.first().banner
					else:
						print(f"Generating user {self.id} avatar from accent_color {self.__accent_color} HEX: {hex(self.__accent_color)[:8]}")
						buf = io.BytesIO()
						img = Image.new("RGB", (512, 180), f"#{hex(self.__accent_color)[2:8].ljust(6, "0")}")
						img.save(buf, format="PNG")
						img = File(buf, "accent.png")
					self.banner = img

			if self.primary_guild and not isinstance(self.primary_guild, int): #Is update from oauth or dbot bot_task
				if not self.tag or self.primary_guild.identity_guild_id != self.tag.id or self.primary_guild.badge.key != self.tag.tag_hash: #Tag changed guilds
					print(f"Updating tag for {self.id}")
					try:
						existing = DiscordTag.objects.get(id=self.primary_guild.identity_guild_id)
					except DiscordTag.DoesNotExist:
						print(f"No existing tag for guild {self.primary_guild.identity_guild_id}")
						existing = DiscordTag(id=self.primary_guild.identity_guild_id)
						existing.badge = self.primary_guild.badge.url
						existing.tag = self.primary_guild.tag
						existing.save()

					if existing.tag_hash not in self.primary_guild.badge.key or existing.tag != self.primary_guild.tag:
						print(f"Tag changed {self.primary_guild.identity_guild_id}")
						existing.badge = self.primary_guild.badge.url
						existing.tag = self.primary_guild.tag
						existing.save()

					self.tag = existing

			if self.accent_color == None and self.__accent_color != None:
				self.accent_color = self.__accent_color

			super().save()
		except Exception:
			print(traceback.format_exc())



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

