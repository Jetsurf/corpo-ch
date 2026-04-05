from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django.shortcuts import redirect, render

from corpoch.discord_oauth.DiscordOAuth import *
from corpoch.models import Match, DiscordUser, DiscordToken

def null(request: HttpRequest):
  return redirect("home")

def home(request: HttpRequest):
	if request.method == "POST":
		try:
			del request.session["access_token"]
		except KeyError:
			pass
	return render(request, "home.html", context={"auth_url" : auth_url_discord})

def auth(request: HttpRequest):
	code = request.GET.get("code")
	if code:# if code is valid
		OAuth = Auth(code=code)
		request.session["access_token"] = OAuth.token
		request.session['refresh_token'] = OAuth.refresh_token
		access_token = OAuth.token
	else:
		access_token = request.session.get("access_token")
	if not access_token:#if token is not exists and not valid
		return redirect(auth_url_discord)# redirect to discord
	return redirect("user")

def user(request: HttpRequest):
	access_token = request.session.get("access_token")
	refresh_token = request.session["refresh_token"]
	if access_token:
		OAuth = Auth()
		try:
			context = { "user" : User(OAuth.user(access_token)), "guilds" : Guilds(OAuth.guilds(access_token)),}
		except AuthError:
			return redirect(auth_url_discord)
	else:
		url = request.build_absolute_uri().split("/")
		url.pop()
		return redirect("/".join([i for i in url]))

	if context:
		discord_user = authenticate(request, user=context['user'])
		if not isinstance(discord_user, DiscordUser):
			discord_user = discord_user[0]
		login(request, discord_user, backend="corpoch.auth.DiscordBackend")
		context['internal_user'] = discord_user
	if DiscordToken.objects.filter(user=request.user.id).exists():
		discord_token = request.user.token
		discord_token.delete()

	token = DiscordToken(access_token=access_token, refresh_token=refresh_token, user=discord_user)
	token.save()

	return render(request, "user.html", context=context)

def livematches(request: HttpRequest):
	matches = list(filter(lambda match: match.ongoing, Match.objects.all()))
	current_match_ids = ",".join([str(m.id) for m in matches])
	
	return render(request, "livematches.html", {
		'matches': matches,
		'current_match_ids': current_match_ids
	})

def update_livematches(request: HttpRequest):
	selected_ids = request.GET.getlist('selected_matches')
	client_match_ids = request.GET.get('current_match_ids', '')

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
