from django.contrib.auth import authenticate, login
from django.shortcuts import render
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

from corpoch.discord_oauth.DiscordOAuth import *
from corpoch.models import Match, DiscordUser

def null(request: HttpRequest):
  return redirect("home")

def home(request: HttpRequest):
	if request.method == "POST":
		try:
			del request.session["access_token"]
		except KeyError:
			pass
	return render(request, "home.html", context={"auth_url" : auth_url_discord})

@login_required(login_url="/auth/login")
def get_authenticated_user(request):
    return JsonResponse({"user": "authenticated"})

def auth(request: HttpRequest):
	code = request.GET.get("code")
	if code:# if code is valid
		OAuth = Auth(code=code)
		request.session["access_token"] = OAuth.token
		access_token = OAuth.token
	else:
		access_token = request.session.get("access_token")
	if not access_token:#if token is not exists and not valid
		return redirect(auth_url_discord)# redirect to discord
	return redirect("user")

def user(request: HttpRequest):
	access_token = request.session.get("access_token")
	if access_token:
		OAuth = Auth()
		try:
			context = { "user" : User(OAuth.user(access_token)), }
		except AuthError:
			return redirect(auth_url_discord)
	else:
		url = request.build_absolute_uri().split("/")
		url.pop()
		return redirect("/".join([i for i in url]))

	if context:
		print(f"HAVE CONTEXT: {context}")
		discord_user = authenticate(request, user=context['user'])
		discord_user = list(discord_user).pop()
		print(f"DISCORD USER {discord_user}")
		login(request, discord_user, backend="corpoch.auth.DiscordBackend")

	return render(request, "user.html", context=context)

def livematches(request: HttpRequest):
	return render(request, "livematches.html")

def update_livematches(request: HttpRequest):
	matches = list(filter(lambda match: match.ongoing, Match.objects.all()))
	return render(request, 'partials/livematchesdata.html', {'matches': matches})
