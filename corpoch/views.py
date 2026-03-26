from django.contrib.auth import authenticate, login
from django.shortcuts import render
from django.http import HttpRequest
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

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

	if DiscordToken.objects.filter(user=request.user.id).exists():
		discord_token = request.user.token
		discord_token.delete()

	token = DiscordToken(access_token=access_token, refresh_token=refresh_token, user=discord_user)
	token.save()

	return render(request, "user.html", context=context)

def livematches(request: HttpRequest):
	return render(request, "livematches.html")

def update_livematches(request: HttpRequest):
	matches = list(filter(lambda match: match.ongoing, Match.objects.all()))
	return render(request, 'partials/livematchesdata.html', {'matches': matches})
