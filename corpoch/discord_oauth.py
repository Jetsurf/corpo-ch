from requests import Session
from dotenv import load_dotenv
import os

load_dotenv()

client_id = os.getenv("BOT_ID")
client_secret =  os.getenv("BOT_SECRET")
auth_url_discord = os.getenv("AUTH_URL_DISCORD")
redirect_uri = os.getenv("REDIRECT_URI")
default_icon_avatar = "https://cdn.discordapp.com/embed/avatars/0.png"

class AuthError(Exception):
	def __init__(self, msg) -> None:
		super().__init__(msg)

class Auth(Session):
	BASE, HEADERS = "https://discord.com/api/v10/", {'Content-Type': 'application/x-www-form-urlencoded'}

	def __init__(self, code=None, access_token=None, refresh_token=None, *args, **kwargs) -> None:
		if not code:
			self.__data = { "client_id": client_id,	"client_secret": client_secret,	"grant_type": "refresh_token",	"refresh_token": refresh_token, "redirect_uri": redirect_uri, }
			self.__token = access_token
			self.__refresh_token = refresh_token
		else:
			self.__data = { "client_id": client_id,	"client_secret": client_secret,	"grant_type": "authorization_code",	"code": code, "redirect_uri": redirect_uri,	}
			self.__token = ""
			self.__refresh_token = ""
		super().__init__(*args, **kwargs)
	
	def __exchange_code(self) -> str:
		response = self.post(self.BASE + "oauth2/token", data=self.__data, headers=self.HEADERS)
		if response.status_code == 200:
			json = response.json()
			self.__token = json["access_token"]
			self.__refresh_token = json["refresh_token"]
			return self.__token
		raise AuthError(f"Failed to connect to discord API {response.json()}")
	
	@property
	def token(self):
		if not self.__token:
			self.__exchange_code()
		return self.__token
	
	@property
	def refresh_token(self):
		if not self.__refresh_token:
			self.__exchange_code()
		return self.__refresh_token

	def user(self, token=None) -> dict:
		if not token:
			try:
				token = self.token
			except AttributeError:
				token = self.__exchange_code()

		response =  self.get(self.BASE + "users/@me", headers={'Authorization': f'Bearer {token}'})
		if response.status_code == 200:
			return response.json()
		raise AuthError("Failed to connect to discord API")

	def guilds(self, token=None) -> list:
		if not token:
			token = self.token
		response = self.get(self.BASE + "users/@me/guilds", headers={'Authorization': f'Bearer {token}'})
		if response.status_code == 200:
			return response.json()
		raise AuthError("Failed to connect to discord API")
		
class User:
	def __init__(self, user : dict) -> None:
		self.__user = user
		for k , v in self.__user.items():
			try:
				setattr(self, k, v)
			except AttributeError:
				continue

	@property
	def avatar(self):
		return f"https://cdn.discordapp.com/avatars/{self.__user['id']}/{self.__user['avatar']}" if self.__user['avatar'] else default_icon_avatar

class Role:
	def __init__(self, role: dict) -> None:
		self.__role = role
		for k, v in self.__role.items():
			try:
				setattr(self, k , v)
			except AttributeError:
				continue

	def __repr__(self) -> str:
		return repr(self.__role)

	def __str__(self):
		return self.name

class Guilds:
	def __init__(self, guilds : list) -> None:
		self.__guilds = []
		from corpoch.models import Tournament
		self.__tournaments = []
		for guild in guilds:
			for tourney in Tournament.objects.all().filter(guild__id=guild['id']):
				self.__guilds.append(guild)
				self.__tournaments.append(tourney)
				
	def __iter__(self):
		return iter([Guild(guild) for guild in self.__guilds])

	def __repr__(self) -> str:
			return repr(self.__guilds)

class Guild:
	def __init__(self, guild : dict) -> None:
		self.__guild = guild
		for k, v in self.__guild.items():
			try:
				setattr(self, k , v)
			except AttributeError:
				continue

	def __repr__(self) -> str:
		return repr(self.__guild)

	@property
	def user_is_administrator(self):
		#Move this to be checking role grants admin from DB
		return self.__guild["permissions"] == '1099511627775'
	
	@property
	def roles(self) -> list:
		return list(Role(role) for role in self.__guild['roles'])

	@property
	def id(self):
		return self.__guild['id']

	@property
	def icon(self):
		return f"https://cdn.discordapp.com/icons/{self.__guild['id']}/{self.__guild['icon']}.png" if self.__guild['icon'] else default_icon_avatar
