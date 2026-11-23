from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from core.models import Project, Task

User = get_user_model()


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        email = attrs.get(self.username_field)
        if email:
            user = User.objects.filter(email__iexact=email).only("username").first()
            if user:
                attrs[self.username_field] = user.get_username()
        return super().validate(attrs)


class RegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=150)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["email", "password", "first_name", "last_name"]

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def create(self, validated_data):
        email = validated_data.pop("email")
        return User.objects.create_user(username=email, email=email, **validated_data)


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name"]
        read_only_fields = ["id", "email"]


class ProjectSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    owner_name = serializers.CharField(source="owner.get_full_name", read_only=True)
    member_ids = serializers.PrimaryKeyRelatedField(
        source="members", queryset=User.objects.all(), many=True, required=False,
        write_only=True,
    )
    members = serializers.SerializerMethodField()
    progress = serializers.IntegerField(read_only=True)
    task_count = serializers.IntegerField(source="tasks.count", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "description", "owner", "owner_name", "members",
            "member_ids", "deadline", "progress", "task_count", "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_members(self, project):
        people = [project.owner, *project.members.all()]
        return [
            {"id": person.id, "name": person.get_full_name() or person.email,
             "email": person.email}
            for person in people
        ]

    def validate(self, attrs):
        if "members" in attrs:
            request = self.context.get("request")
            project = self.instance
            if project and request and project.owner_id != request.user.id:
                raise serializers.ValidationError(
                    {"member_ids": "Only the project owner can manage members."}
                )
        return attrs


class TaskSerializer(serializers.ModelSerializer):
    assignee_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id", "project", "project_name", "title", "description", "assignee",
            "assignee_name", "created_by", "due_date", "status", "priority",
            "task_type", "estimated_days", "completed_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "completed_at", "created_at", "updated_at"]

    def get_assignee_name(self, task):
        if task.assignee is None:
            return None
        return task.assignee.get_full_name() or task.assignee.email

    def validate_project(self, project):
        user = self.context["request"].user
        if not Project.objects.filter(
            Q(owner=user) | Q(members=user), pk=project.pk
        ).exists():
            raise serializers.ValidationError("Select a project you belong to.")
        return project

    def validate(self, attrs):
        project = attrs.get("project", getattr(self.instance, "project", None))
        assignee = attrs.get("assignee", getattr(self.instance, "assignee", None))
        if assignee and project and assignee != project.owner:
            if not project.members.filter(pk=assignee.pk).exists():
                raise serializers.ValidationError(
                    {"assignee": "The assignee must be a member of this project."}
                )
        return attrs


class TeamMemberSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    project_ids = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "name", "project_ids"]

    def get_name(self, user):
        return user.get_full_name() or user.email

    def get_project_ids(self, user):
        current_user = self.context["request"].user
        return list(
            Project.objects.filter(
                Q(owner=current_user) | Q(members=current_user)
            ).filter(
                Q(owner=user) | Q(members=user)
            ).values_list("id", flat=True).distinct()
        )


class TeamInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    project_id = serializers.IntegerField()

    def validate(self, attrs):
        user = self.context["request"].user
        try:
            project = Project.objects.get(pk=attrs["project_id"], owner=user)
        except Project.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"project_id": "Only an owned project can add team members."}
            ) from exc
        try:
            member = User.objects.get(email__iexact=attrs["email"].strip())
        except User.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"email": "No registered account uses this email address."}
            ) from exc
        if member == user:
            raise serializers.ValidationError({"email": "You already own this project."})
        attrs["project"] = project
        attrs["member"] = member
        return attrs
