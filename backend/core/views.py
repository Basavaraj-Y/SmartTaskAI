import logging

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Project, Task
from core.serializers import (
    ProfileSerializer,
    ProjectSerializer,
    RegistrationSerializer,
    TaskSerializer,
    TeamInviteSerializer,
    TeamMemberSerializer,
    EmailTokenObtainPairSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": ProfileSerializer(user).data,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"refresh": "This field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(refresh_token).blacklist()
        except (TokenError, ValueError, TypeError):
            return Response(
                {"refresh": "The refresh token is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_205_RESET_CONTENT)


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        user = self.request.user
        return Project.objects.filter(Q(owner=user) | Q(members=user)).distinct().select_related(
            "owner"
        ).prefetch_related("members")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        if instance.owner_id != self.request.user.id:
            raise PermissionDenied("Only the project owner can delete a project.")
        instance.delete()


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer

    def get_queryset(self):
        user = self.request.user
        return Task.objects.filter(
            Q(project__owner=user) | Q(project__members=user)
        ).distinct().select_related("project", "assignee", "created_by")

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class TeamView(APIView):
    def get(self, request):
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(members=request.user)
        ).distinct()
        project_ids = projects.values_list("id", flat=True)
        member_ids = User.objects.filter(
            Q(owned_projects__in=project_ids) | Q(team_projects__in=project_ids)
        ).exclude(pk=request.user.pk).distinct()
        return Response(TeamMemberSerializer(
            member_ids, many=True, context={"request": request}
        ).data)

    def post(self, request):
        serializer = TeamInviteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        values["project"].members.add(values["member"])
        return Response(
            TeamMemberSerializer(
                values["member"], context={"request": request}
            ).data,
            status=status.HTTP_201_CREATED,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    projects = Project.objects.filter(
        Q(owner=request.user) | Q(members=request.user)
    ).distinct()
    tasks = Task.objects.filter(project__in=projects).select_related(
        "project", "assignee"
    )
    today = timezone.localdate()
    counts = tasks.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=Task.Status.DONE)),
        in_progress=Count("id", filter=Q(status=Task.Status.IN_PROGRESS)),
        todo=Count("id", filter=Q(status=Task.Status.TODO)),
        overdue=Count(
            "id",
            filter=Q(due_date__lt=today) & ~Q(status=Task.Status.DONE),
        ),
    )
    priority_counts = {
        row["priority"]: row["count"]
        for row in tasks.values("priority").annotate(count=Count("id"))
    }
    project_data = [
        {
            "id": project.id,
            "name": project.name,
            "deadline": project.deadline,
            "progress": project.progress,
            "task_count": project.tasks.count(),
        }
        for project in projects.order_by("deadline", "name")[:8]
    ]
    upcoming = tasks.exclude(status=Task.Status.DONE).order_by("due_date", "-created_at")[:8]
    return Response(
        {
            "projects_count": projects.count(),
            "tasks_count": counts["total"],
            "completed_count": counts["completed"],
            "in_progress_count": counts["in_progress"],
            "pending_count": counts["todo"],
            "overdue_count": counts["overdue"],
            "priority_breakdown": priority_counts,
            "projects": project_data,
            "upcoming_tasks": TaskSerializer(upcoming, many=True).data,
        }
    )


class PredictionSerializerMixin:
    def predict(self, function, **values):
        try:
            result = function(**values)
        except FileNotFoundError as exc:
            return Response(
                {"detail": str(exc), "code": "model_not_trained"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except (OSError, RuntimeError, ValueError):
            logger.exception("Unable to load or run model %s", function.__name__)
            return Response(
                {
                    "detail": "The trained model artifact could not be loaded. Retrain the models and try again.",
                    "code": "model_artifact_error",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        logger.info("Completed %s prediction for user %s", function.__name__, self.request.user.pk)
        return Response(result)


class PriorityPredictionView(PredictionSerializerMixin, APIView):
    class InputSerializer(serializers.Serializer):
        description = serializers.CharField(max_length=4000)
        task_type = serializers.ChoiceField(
            choices=["bug", "improvement", "new_feature", "other"], default="other"
        )

    def post(self, request):
        from core.ml import predict_priority

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.predict(predict_priority, **serializer.validated_data)


class CompletionPredictionView(PredictionSerializerMixin, APIView):
    class InputSerializer(serializers.Serializer):
        complexity = serializers.IntegerField(min_value=1, max_value=5, default=3)
        effort_points = serializers.IntegerField(min_value=1, default=5)
        team_size = serializers.IntegerField(min_value=1, default=1)
        dependencies = serializers.IntegerField(min_value=0, default=0)

    def post(self, request):
        from core.ml import predict_completion

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.predict(predict_completion, **serializer.validated_data)


class DelayPredictionView(PredictionSerializerMixin, APIView):
    class InputSerializer(serializers.Serializer):
        progress = serializers.FloatField(min_value=0, max_value=100)
        completed = serializers.IntegerField(min_value=0, default=0)
        pending = serializers.IntegerField(min_value=0, default=0)
        days_until_deadline = serializers.IntegerField(default=30)
        overdue = serializers.IntegerField(min_value=0, default=0)
        complexity = serializers.IntegerField(min_value=1, max_value=5, default=3)

    def post(self, request):
        from core.ml import predict_delay

        serializer = self.InputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.predict(predict_delay, **serializer.validated_data)
