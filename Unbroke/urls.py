
from django.contrib import admin
from django.urls import path, include
from core.views import (
    LandingView,
    StatementCreateView,
    get_progress,
    generate_advice,
    UserProfileView,
    StatementDetailView,
    StatementDeleteView
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', LandingView.as_view(), name='home'),
    path("", include("users.urls")),
    path("upload/", StatementCreateView.as_view(), name="statement_upload"),
    path("progress/<str:task_id>/", get_progress, name="get_progress"),
    path('generate_advice/<str:task_id>/', generate_advice, name='generate_advice'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('statement/<int:pk>/', StatementDetailView.as_view(), name='statement_detail'),
    path('statement/<int:pk>/delete/', StatementDeleteView.as_view(), name='statement_delete'),
]
