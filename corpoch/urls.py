from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include, reverse_lazy

from corpoch import views
from corpoch.api import urls as apiurls

urlpatterns = [
    path('admin/login/', views.auth, name='login'),
    path('admin/', admin.site.urls),
    path('', views.null),
    path('auth',views.auth),
    path('auth/user', views.user, name="user"),
    path('home', views.home, name="home"),
    path('api/', include('corpoch.api.urls')),
    path('livematches/', views.livematches, name="livematches"),
    path('privterms/', views.privterms, name="privterms"),
    path('chart/<chart_pk>', views.chart, name="chart"),
    path('profile/<user_pk>', views.profile, name="profile"),
    path('tournament/<tournament_pk>/<bracket_pk>', views.bracket_view, name="bracket"),
    path('tournament/<tournament_pk>', views.tournament_view, name="tournament"),
    path("match/<match_pk>/<round_pk>", views.round, name="round"),
    path("match/<match_pk>", views.match, name="match"),
    path('update-live-matches/', views.update_livematches, name='update_livematches'),
    path('update-search/', views.update_search, name="update-search")
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)