from django.urls import include, path

from drf_yasg.views import get_schema_view
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg import openapi
from rest_framework import permissions
from rest_framework import routers

from corpoch.api import views

class HttpsSchemaGenerator(OpenAPISchemaGenerator):
    def get_schema(self, request=None, public=False):
        schema = super().get_schema(request, public)
        schema.schemes = ["https"]
        return schema

schema_view = get_schema_view(
	openapi.Info(
		title="Corpo CH API",
		default_version='v1',
		description="API to pull most data out of Corpo.",
		terms_of_service="https://corpo-ch.org/privterms",
		contact=openapi.Contact(email="crmeade@mtu.edu"),
		license=openapi.License(name="MIT License"),
	),
	generator_class=HttpsSchemaGenerator,
	public=True,
	permission_classes=(permissions.IsAuthenticatedOrReadOnly,),
)

router = routers.DefaultRouter()
router.register(r"discord/users", views.DiscordUserViewSet)
router.register(r"discord/guilds", views.DiscordGuildViewSet)
router.register(r"discord/channels", views.DiscordChannelViewSet)
router.register(r"discord/roles", views.DiscordRoleViewSet)
router.register(r"matches", views.MatchViewSet)
router.register(r"players", views.TournamentPlayerViewSet)
router.register(r"brackets", views.BracketViewSet)
router.register(r"groups", views.GroupViewSet)
router.register(r"seeding", views.GroupSeedViewSet)

urlpatterns = [
	path("", include(router.urls)),
	path("auth/", include("rest_framework.urls", namespace="rest_framework")),
	path('swagger.json/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
	path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
	path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]
