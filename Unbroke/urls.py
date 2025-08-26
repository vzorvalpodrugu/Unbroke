
from django.contrib import admin
from django.urls import path, include
from core.views import (
    LandingView,
    StatementCreateView,
    get_progress
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', LandingView.as_view(), name='landing'),
    path("", include("users.urls")),
    path("upload/", StatementCreateView.as_view(), name="statement_upload"),
    path("progress/<str:task_id>/", get_progress, name="get_progress"),
]
