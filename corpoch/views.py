from requests import Session

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, Http404
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

def chart(request: HttpRequest, chart_pk):
	from corpoch.models import Chart
	if not chart_pk or chart_pk == "None":
		return HttpResponse(f"Can't find a chart if you don't provide one!", status=404)
	else:
		chart = get_object_or_404(Chart, pk=chart_pk)

	context = { "logged_in_user" : logged_in_user(request), "chart" : chart, "stats" : chart.leaderboard_stats }
	return render(request, "chart.html", context=context)

def profile(request: HttpRequest, user_pk):
	from corpoch.models import DiscordUser, Tournament, TournamentPlayer
	if not user_pk or user_pk == "None":
		return HttpResponse(f"Can't find a user if you don't provide one!", status=404)
	else:
		user = get_object_or_404(DiscordUser, pk=user_pk)

	#way to stitch together user to all their tournament player objects/references
	tournaments = []
	for tournament in Tournament.objects.all().order_by('-id'):
		ret = {
			'tournament' : tournament,
			'player' : None,
			'is_staff' : False,
			'is_ref' : False
		}
		try:
			ret['player'] = tournament.players.get(user=user)
		except TournamentPlayer.DoesNotExist:
			pass
		try:
			temp = tournament.guild.admins.get(id=user.id)
			ret['is_staff'] = True
		except DiscordUser.DoesNotExist:
			pass
		try:
			temp = tournament.guild.referees.get(id=user.id)
			ret['is_ref'] = True
		except DiscordUser.DoesNotExist:
			pass

		tournaments.append(ret)

	context = { "user" : user, "tournies": tournaments, "logged_in_user" : logged_in_user(request) }
	return render(request, "profile.html", context=context)

def match(request: HttpRequest, match_pk):
	from corpoch.models import Match
	if not match_pk or match_pk == "None":
		return HttpResponse(f"Can't find a match if you don't provide one!", status=404)
	else:
		match = get_object_or_404(Match, pk=match_pk)

	context = { "logged_in_user" : logged_in_user(request), "match" : match, "rounds" : match.match_rounds.all() }
	return render(request, "match.html", context=context)

def round(request: HttpRequest, match_pk, round_pk):
	from corpoch.models import Match, MatchRound
	if not match_pk or match_pk == "None":
		return HttpResponse(f"Can't find a match if you don't provide one!", status=404)
	else:
		match = get_object_or_404(Match, pk=match_pk)

	if not round_pk or round_pk == "None":
		return HttpResponse(f"Can't find a round if you don't provide one!", status=404)
	else:
		round = get_object_or_404(MatchRound, pk=round_pk)

	context = { "logged_in_user" : logged_in_user(request), "match" : match, "round" : round }
	return render(request, "round.html", context=context)

def tournament_view(request: HttpRequest, tournament_pk):
	from corpoch.models import Tournament, Bracket
	if not tournament_pk or tournament_pk == "None":
		return HttpResponse("Can't find a tournament if you don't provide one!", status=404)
	else:
		tourney = get_object_or_404(Tournament, short_name=tournament_pk)

	context = {	'logged_in_user' : logged_in_user(request),	'tournament' : tourney,	}
	return render(request, "tournament.html", context=context)

def bracket_view(request: HttpRequest, tournament_pk, bracket_pk):
	from corpoch.models import Tournament, Bracket
	if not tournament_pk or tournament_pk == "None":
		return HttpResponse("Can't find a tournament if you don't provide one!", status=404)
	else:
		tournament = get_object_or_404(Tournament, short_name=tournament_pk)

	if not bracket_pk or bracket_pk == "None":
		return HttpResponse("Can't find a bracket if you don't provide one!", status=404)
	else:
		try:
			bracket = Bracket.objects.get(tournament=tournament, name=bracket_pk)
		except Bracket.DoesNotExist:
			return Http404("Bracket found/valid")

	context = { 'logged_in_user' : logged_in_user(request), 'bracket' : bracket }
	return render(request, "bracket.html", context=context)

def group_view(request: HttpRequest, tournament_pk, bracket_pk, group_pk):
	from corpoch.models import Tournament, Bracket, Group
	if not tournament_pk or tournament_pk == "None":
		return HttpResponse("Can't find a tournament if you don't provide one!", status=404)
	else:
		tournament = get_object_or_404(Tournament, short_name=tournament_pk)

	if not bracket_pk or bracket_pk == "None":
		return HttpResponse("Can't find a bracket if you don't provide one!", status=404)
	else:
		try:
			bracket = Bracket.objects.get(tournament=tournament, name=bracket_pk)
		except Bracket.DoesNotExist:
			return Http404("Bracket found/valid")

	if not group_pk or group_pk == "None":
		return HttpResponse("Can't find a group if you don't provide one!", status=404)
	else:
		try:
			group = Group.objects.get(bracket=bracket, name=group_pk)
		except Group.DoesNotExist:
			return Http404("Group not found/valid")

	context = { 'logged_in_user' : logged_in_user(request), 'group' : group }
	return render(request, "group.html", context=context)

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
	from corpoch.models import DiscordUser, Chart, Tournament
	search = request.GET.get('search', '')
	context = {
		'users' : DiscordUser.objects.none(),
		'charts' : DiscordUser.objects.none(),
		'tournaments': Tournament.objects.none(),
		'count' : 0
	}

	if len(search) < 3:
		return render(request, 'partials/search-partial.html', context=context)
	
	context['users'] = DiscordUser.objects.filter(global_name__icontains=search)
	context['charts'] = Chart.objects.filter(name__icontains=search)
	context['tournaments'] = Tournament.objects.filter(short_name__icontains=search)
	context['count'] = context['users'].count() + context['charts'].count() + context['tournaments'].count()
	return render(request, 'partials/search-partial.html', context=context)

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
