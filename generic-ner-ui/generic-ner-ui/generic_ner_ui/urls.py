"""generic_ner_ui URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from decorator_include import decorator_include
from django.conf.urls import url
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LogoutView
from django.http import JsonResponse
from django.urls import include, path, re_path

from generic_ner_ui import settings
from generic_ner_ui.utils import redirect


def health_check(request):
    return JsonResponse({"status": "up"})


urlpatterns = [
    re_path(r'^$', lambda _: redirect('/main')),
    path('', include('social_django.urls', namespace='social')),
    path('admin/', admin.site.urls),
    path('main/', decorator_include(login_required, ('main.urls', "main"),
                                    namespace="main")),
    path('health', health_check),
    url(r'^logout/$', LogoutView.as_view(), {'next_page': settings.LOGOUT_REDIRECT_URL}, name='logout'),
]
