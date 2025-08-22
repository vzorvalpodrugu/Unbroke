
from django.contrib import admin
from django.urls import path, include
from core.views import (
    LandingView
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', LandingView.as_view(), name='landing'),
    path("", include("users.urls")),
]
