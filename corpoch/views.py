from requests import Session

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone

from corpoch import settings
from corpoch.dbot.tasks import update_user

def null(request: HttpRequest):
  return redirect("home")

def home(request: HttpRequest):
	if request.method == "POST":
		try:
			request.session.clear()
		except KeyError:
			pass

	return render(request, "home.html", context={"auth_url" : settings.AUTH_URL_DISCORD, 'logged_in_user' : logged_in_user(request)})

def auth(request: HttpRequest):
	from corpoch.models import DiscordUser, DiscordToken
	code = request.GET.get("code")
	if code:# if code is valid
		oauth = DiscordToken()
		oauth.login(code=code)
		identity = oauth.identity()
		request.session["access_token"] = oauth.access_token
		request.session['user_id'] = identity['id']

		try:
			token = DiscordToken.objects.get(user__id=identity['id'])
			token.access_token = oauth.access_token
			token.refresh_token = oauth.refresh_token
			token.expires = oauth.expires
			token.save()
			oauth = token
		except DiscordToken.DoesNotExist:
			oauth.user, created = DiscordUser.objects.get_or_create(pk=identity['id'])
			update_user(identity['id'])
			oauth.save()
	else:
		if logged_in_user(request):
			oauth = DiscordUser.objects.get(id=logged_in_user(request).id).token
		else:
			oauth = None

	if not oauth:
		return redirect(settings.AUTH_URL_DISCORD)
	return redirect("user")

def user(request: HttpRequest):
	from corpoch.models import DiscordToken, DiscordUser
	from corpoch.dbot.models import Guilds
	if request.session.get("access_token"):
		user = DiscordUser.objects.get(id=request.session.get('user_id'))
		token = DiscordToken.objects.get(user__id=request.session.get('user_id'))
		#If post w/ guild_id as param, do guild join
		if request.method == "POST":
			guild_id = request.GET.get("guild_id")
			try:
				guild = Guilds.objects.get(id=guild_id)
				token.invite_to_guild(guild) #Do the invite
			except Guilds.DoesNotExist:
				pass
		else:
			token.login()

		try:
			context = { "user" : user, "guilds" : TournamentGuilds(user) }
		except DiscordToken.AuthError:
			return redirect(settings.AUTH_URL_DISCORD)
	else:
		return redirect(settings.AUTH_URL_DISCORD)

	discord_user = authenticate(request, user=context['user'])
	if not isinstance(discord_user, DiscordUser):
		discord_user = discord_user[0]
	login(request, discord_user, backend="corpoch.auth.DiscordBackend")
	context['logged_in_user'] = discord_user
	return render(request, "user.html", context=context)

def profile(request: HttpRequest, user_pk):
	from corpoch.models import DiscordUser, Match, MatchRound
	if not user_pk or user_pk == "None":
		return HttpResponse(f"Can't find a user if you don't provide one!", status=404)
	else:
		user = get_object_or_404(DiscordUser, pk=user_pk)



	context = { "user" : user, "guilds": TournamentGuilds(user), "logged_in_user" : logged_in_user(request), "stats" : user.career_stats, "users" : [] }
	return render(request, "profile.html", context=context)

def livematches(request: HttpRequest):
	from corpoch.models import Match, DiscordUser

	matches = list(filter(lambda match: match.ongoing, Match.objects.all()))
	current_match_ids = ",".join([str(m.id) for m in matches])
	return render(request, "livematches.html", {
		'matches': matches,
		'current_match_ids': current_match_ids,
		'logged_in_user' : logged_in_user(request)
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

def update_search(request: HttpRequest):
	search = request.GET.get('user-search', '')
	if len(search) < 3:
		return render(request, 'partials/search-partial.html', { 'users' : DiscordUser.objects.none(), "count" : 0 })
	from corpoch.models import DiscordUser
	users = DiscordUser.objects.filter(global_name__icontains=search)
	search_count = users.count()
	return render(request, 'partials/search-partial.html', { 'users' : users, "count" : search_count })

def privterms(request: HttpRequest):
	return render(request, 'privterms.html', context={'logged_in_user' : logged_in_user(request)})

def logged_in_user(request: HttpRequest):
	'''
	Meant to not be a direct view, rather a function to return the currently logged in user
	'''
	from corpoch.models import DiscordUser
	if 'access_token' not in request.session:
		return None
	try:
		return DiscordUser.objects.get(id=request.session['user_id'])
	except:
		return None

class TournamentGuilds:

	def __init__(self, user) -> None:
		self.__guilds = []
		self.__user = user
		try:
			oauth_guilds = self.__user.token.guilds() #Trigger refresh of OAUTH guilds in Token Model
		except:
			oauth_guilds = []
		from corpoch.models import Tournament
		for tournament in Tournament.objects.all().order_by("-id"):
			oauth = None
			for guild in oauth_guilds:
				if int(guild['id']) == tournament.guild.id:
					oauth = guild
					break
			tmp = Guild(user, tournament, oauth_guild=oauth)
			if tmp not in self.__guilds:
				self.__guilds.append(tmp)
				
	def __iter__(self):
		return iter([guild for guild in self.__guilds])

	def __repr__(self) -> str:
			return repr(self.__guilds)

	@property
	def user_id(self):
		if self.__user:
			return self.__user.id
		else:
			return None

class Guild:
	def __init__(self, user, tournament, oauth_guild=None) -> None:
		self.__user = None
		self.__player = None
		self.__guild = tournament.guild
		self.__oauth_guild = oauth_guild
		self.__tournament = tournament

		self.__user = user
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
		if self.__guild.icon:
			return self.__guild.icon
		else:
			return "https://cdn.discordapp.com/embed/avatars/0.png"

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

	@property
	def is_staff(self):
		try:
			admin = self.__guild.admins.get(id=self.__user.id)
			return True
		except:
			return False

	@property
	def is_referee(self):
		try:
			ref = self.__guild.referees.get(id=self.__user.id)
			return True
		except:
			return False

	@property
	def is_member(self):
		if self.__oauth_guild:
			return True
		else:
			return False