from requests import Session

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.utils import timezone

from corpoch import settings
from corpoch.dbot.tasks import update_user

def null(request: HttpRequest):
  return redirect("home")

def home(request: HttpRequest):
	if request.method == "POST":
		try:
			del request.session["access_token"]
		except KeyError:
			pass
	return render(request, "home.html", context={"auth_url" : settings.AUTH_URL_DISCORD})

def auth(request: HttpRequest):
	from corpoch.models import DiscordUser, DiscordToken
	code = request.GET.get("code")
	if code:# if code is valid
		oauth = DiscordToken()
		oauth.login(code=code)

		request.session["access_token"] = oauth.access_token
		user = OAuthUser(oauth.identity())
		request.session['user_id'] = user.id
		try:
			token = DiscordToken.objects.get(user__id=user.id)
			token.access_token = oauth.access_token
			token.refresh_token = oauth.refresh_token
			token.expires = oauth.expires
			token.save()
			oauth = token
		except DiscordToken.DoesNotExist:
			oauth.user, created = DiscordUser.objects.get_or_create(pk=user.id)
			if created:
				update_user(user.id)
			oauth.save()
	else:
		access_token = request.session.get("access_token")
	if not oauth.access_token:
		return redirect(settings.AUTH_URL_DISCORD)
	return redirect("user")

def user(request: HttpRequest):
	from corpoch.models import DiscordToken, DiscordUser
	if request.session.get("access_token"):
		oauth = DiscordToken.objects.get(user__id=request.session.get('user_id'))
		try:
			oauth.login()
			user = OAuthUser(oauth.identity())
			context = { "user" : user, "guilds" : TournamentGuilds(user) }
			oauth.save()
		except DiscordToken.AuthError:
			return redirect(auth_url_discord)
	else:
		url = request.build_absolute_uri().split("/")
		url.pop()
		return redirect("/".join([i for i in url]))

	discord_user = authenticate(request, user=context['user'])
	if not isinstance(discord_user, DiscordUser):
		discord_user = discord_user[0]
	login(request, discord_user, backend="corpoch.auth.DiscordBackend")
	context['internal_user'] = discord_user

	return render(request, "user.html", context=context)

def livematches(request: HttpRequest):
	from corpoch.models import Match
	matches = list(filter(lambda match: match.ongoing, Match.objects.all()))
	current_match_ids = ",".join([str(m.id) for m in matches])

	return render(request, "livematches.html", {
		'matches': matches,
		'current_match_ids': current_match_ids
	})

def update_livematches(request: HttpRequest):
	selected_ids = request.GET.getlist('selected_matches')
	client_match_ids = request.GET.get('current_match_ids', '')
	from corpoch.models import Match
	all_ongoing = list(filter(lambda match: match.ongoing, Match.objects.all()))
	current_match_ids = ",".join([str(m.id) for m in all_ongoing])

	matches_changed = (client_match_ids != current_match_ids)

	display_matches = all_ongoing
	if selected_ids and any(selected_ids):
		display_matches = [m for m in all_ongoing if str(m.id) in selected_ids]

	return render(request, 'partials/livematchesdata.html', {
		'matches': display_matches,
		'all_matches': all_ongoing,
		'selected_ids': selected_ids,
		'matches_changed': matches_changed,
		'current_match_ids': current_match_ids
	})

def privterms(request: HttpRequest):
	return render(request, 'privterms.html')

class OAuthUser:
	__default_avatar = "https://cdn.discordapp.com/embed/avatars/0.png"

	def __init__(self, user : dict) -> None:
		self.__user = user
		for k , v in self.__user.items():
			try:
				setattr(self, k, v)
			except AttributeError:
				continue

	@property
	def id(self):
		return self.__user['id']

	@property
	def avatar(self):
		return f"https://cdn.discordapp.com/avatars/{self.__user['id']}/{self.__user['avatar']}" if self.__user['avatar'] else self.__default_avatar

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

class TournamentGuilds:

	def __init__(self, user : OAuthUser) -> None:
		self.__guilds = []
		self.__user = user
		from corpoch.models import Tournament
		for tournament in Tournament.objects.all():
			tmp = Guild(user, tournament)
			if tmp not in self.__guilds:
				self.__guilds.append(tmp)
				
	def __iter__(self):
		return iter([guild for guild in self.__guilds])

	def __repr__(self) -> str:
			return repr(self.__guilds)

	@property
	def user_id(self):
		return self.__user.id

class Guild:
	__default_avatar = "https://cdn.discordapp.com/embed/avatars/0.png"

	def __init__(self, user : OAuthUser, tournament : Tournament) -> None:
		self.__player = None
		self.__guild = tournament.guild
		self.__tournament = tournament
		from corpoch.models import TournamentPlayer
		try:
			self.__player = TournamentPlayer.objects.get(user__id=user.id, tournament=tournament)
		except TournamentPlayer.DoesNotExist:
			pass

	def __repr__(self) -> str:
		return repr(self.__guild)

	def __str__(self):
		return f"{self.__tournament.name}"

	@property
	def active(self):
		if self.__player:
			return self.__player.active
		else:
			return False

	@property
	def icon(self):
		return f"{self.__guild.icon}" if self.__guild.icon else self.__default_avatar

	@property
	def id(self):
		return self.__guild.id

	@property
	def player(self):
		return self.__player

	@property
	def match_stats(self):
		if self.__player:
			from corpoch.models import Match
			print(f"Sanity: {self.__tournament} - {self.__player}")
			wins = Match.objects.filter(group__bracket__tournament=self.__tournament, winner=self.__player).count()
			losses = Match.objects.filter(group__bracket__tournament=self.__tournament, loser=self.__player).count()
			return f"{wins}W - {losses}L"
		else:
			return f"N/A"

	@property
	def round_stats(self):
		if self.player:
			from corpoch.models import MatchRound
			wins = MatchRound.objects.all().filter(match__group__bracket__tournament=self.__tournament, winner=self.player).count()
			losses = MatchRound.objects.all().filter(match__group__bracket__tournament=self.__tournament, loser=self.player).count()
			return f"{wins}W - {losses}L"
		else:
			return f"N/A"		

	@property
	def tournament(self):
		return self.__tournament

	@property
	def qualifier_active(self):
		from corpoch.models import Qualifier
		qualis = Qualifier.objects.select_related().all().filter(tournament=self.tournament, end_time__gte=timezone.now()).count()

		if qualis > 0:
			return True
		else:
			return False
