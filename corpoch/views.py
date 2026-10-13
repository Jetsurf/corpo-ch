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
			del request.session["access_token"]
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
			if created:
				update_user(identity.id)
			oauth.save()
	else:
		#access_token = request.session.get("access_token")
		if logged_in_user(request):
			oauth = DiscordUser.objects.get(id=logged_in_user(request).id).token
		else:
			oauth = None

	if not oauth:
		return redirect(settings.AUTH_URL_DISCORD)
	return redirect("user")

def user(request: HttpRequest):
	from corpoch.models import DiscordToken, DiscordUser
	if request.session.get("access_token"):
		user = DiscordUser.objects.get(id=request.session.get('user_id'))
		token = DiscordToken.objects.get(user__id=request.session.get('user_id'))
		try:
			token.login()
			context = { "user" : user, "guilds" : TournamentGuilds(user) }
			token.save()
		except DiscordToken.AuthError:
			return redirect(settings.AUTH_URL_DISCORD)
	else:
		url = request.build_absolute_uri().split("/")
		url.pop()
		#return redirect("/".join([i for i in url]))
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

			if player.check_ch_name(round.steg.players[0].profile_name):
				ply_steg = round.steg.players[0]
			else:
				ply_steg = round.steg.players[1]

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
			rounds.append(round)

	stats['score'] = f"{stats['score']:,}"
	stats['match_percent'] = f"{(stats['match_wins'] / (stats['match_wins'] + stats['match_loss']) * 100):.2f}%"
	stats['song_percent'] = f"{(stats['song_wins'] / (stats['song_wins'] + stats['song_loss']) * 100):.2f}%"
	stats['notes_percent'] = f"{(stats['notes_hit'] / stats['notes_total'] * 100):.2f}%"
	stats['phrases_percent'] = f"{stats['phrases_hit'] / stats['phrases_total'] * 100:.2f}%"

	stats['phrases_hit'] = f"{stats['phrases_hit']:,}"
	stats['phrases_total'] = f"{stats['phrases_total']:,}"
	stats['songs_total'] = stats['song_wins'] + stats['song_loss']
	stats['miss_average'] = f"{(stats['notes_total'] - stats['notes_hit']) / stats['songs_total']:.1f}"
	stats['notes_hit'] = f"{stats['notes_hit']:,}"
	stats['notes_total'] = f"{stats['notes_total']:,}"
	stats['ghosts_average'] = f"{stats['ghosts'] / stats['songs_total']:.1f}"
	stats['streak']['notes'] = f"{stats['streak']['notes']:,}"

	context = { "user" : user, "guilds": TournamentGuilds(user), "rounds" : rounds, "logged_in_user" : logged_in_user(request), "stats" : stats, "users" : [] }
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

		from corpoch.models import Tournament
		for tournament in Tournament.objects.all().order_by("-id"):

			#Change me to not be wrapped, was a workaround having class vars static
			tmp = Guild(user, tournament)
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
