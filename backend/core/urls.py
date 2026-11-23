from django.urls import include, path
from rest_framework.routers import DefaultRouter

from core.views import (
    CompletionPredictionView,
    DelayPredictionView,
    LogoutView,
    PriorityPredictionView,
    ProfileView,
    ProjectViewSet,
    RegisterView,
    TaskViewSet,
    TeamView,
    dashboard,
)

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("tasks", TaskViewSet, basename="task")

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/me/", ProfileView.as_view(), name="profile"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("team/", TeamView.as_view(), name="team"),
    path("predictions/priority/", PriorityPredictionView.as_view(), name="priority-prediction"),
    path("predictions/completion/", CompletionPredictionView.as_view(), name="completion-prediction"),
    path("predictions/delay/", DelayPredictionView.as_view(), name="delay-prediction"),
    path("", include(router.urls)),
]
