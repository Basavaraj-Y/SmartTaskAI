from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import Project, Task

User = get_user_model()


class ApplicationApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner@example.com", email="owner@example.com", password="Testing-123!"
        )
        self.client.force_authenticate(self.user)

    def test_health_endpoint_is_public(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")

    def test_project_task_and_dashboard_flow(self):
        project_response = self.client.post(
            "/api/projects/",
            {"name": "Launch", "description": "First release", "deadline": "2030-05-01"},
            format="json",
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.data["id"]

        task_response = self.client.post(
            "/api/tasks/",
            {
                "project": project_id,
                "title": "Ship the API",
                "task_type": "bug",
                "due_date": (timezone.localdate() - timedelta(days=1)).isoformat(),
                "priority": "high",
            },
            format="json",
        )
        self.assertEqual(task_response.status_code, 201)

        dashboard = self.client.get("/api/dashboard/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.data["projects_count"], 1)
        self.assertEqual(dashboard.data["tasks_count"], 1)
        self.assertEqual(dashboard.data["overdue_count"], 1)

        task = Task.objects.get(pk=task_response.data["id"])
        task.status = Task.Status.DONE
        task.save()
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(self.client.get("/api/dashboard/").data["completed_count"], 1)
        self.assertEqual(self.client.get(f"/api/projects/{project_id}/").data["progress"], 100)

    def test_project_and_task_data_are_scoped_to_membership(self):
        private_user = User.objects.create_user(
            username="private@example.com", email="private@example.com", password="Testing-123!"
        )
        project = Project.objects.create(name="Private", owner=private_user)
        Task.objects.create(project=project, title="Private task", created_by=private_user)

        self.assertEqual(self.client.get("/api/projects/").data, [])
        self.assertEqual(self.client.get("/api/tasks/").data, [])
        response = self.client.post(
            "/api/tasks/",
            {"project": project.pk, "title": "Unauthorized"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_project_members_can_collaborate_but_cannot_delete_owner_project(self):
        member = User.objects.create_user(
            username="member@example.com", email="member@example.com", password="Testing-123!"
        )
        project = Project.objects.create(name="Shared", owner=self.user)
        project.members.add(member)
        self.client.force_authenticate(member)
        self.assertEqual(self.client.get(f"/api/projects/{project.pk}/").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/projects/{project.pk}/").status_code, 403)

    def test_registration_returns_jwt_and_rejects_duplicate_email(self):
        self.client.force_authenticate(user=None)
        payload = {
            "email": "new@example.com",
            "password": "Strong-password-923!",
            "first_name": "New",
        }
        response = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["access"])
        self.assertEqual(response.data["user"]["email"], payload["email"])
        self.assertEqual(
            self.client.post("/api/auth/register/", payload, format="json").status_code, 400
        )

    def test_registration_rejects_email_longer_than_username_field(self):
        self.client.force_authenticate(user=None)
        email = f'{"a" * 60}@{"b" * 50}.{"c" * 40}.com'
        response = self.client.post(
            "/api/auth/register/",
            {"email": email, "password": "Strong-password-923!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_login_profile_update_and_refresh_token_logout(self):
        self.client.force_authenticate(user=None)
        login = self.client.post(
            "/api/auth/token/",
            {"username": self.user.email.upper(), "password": "Testing-123!"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        profile = self.client.patch(
            "/api/auth/me/", {"first_name": "Ada"}, format="json"
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.data["first_name"], "Ada")

        logout = self.client.post(
            "/api/auth/logout/", {"refresh": login.data["refresh"]}, format="json"
        )
        self.assertEqual(logout.status_code, 205)
        self.assertEqual(
            self.client.post(
                "/api/auth/token/refresh/",
                {"refresh": login.data["refresh"]},
                format="json",
            ).status_code,
            401,
        )

    def test_owner_can_add_an_existing_user_to_a_project(self):
        member = User.objects.create_user(
            username="collaborator@example.com",
            email="collaborator@example.com",
            password="Testing-123!",
        )
        project = Project.objects.create(name="Shared", owner=self.user)
        response = self.client.post(
            "/api/team/",
            {"email": member.email, "project_id": project.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(project.members.filter(pk=member.pk).exists())
        self.assertEqual(len(response.data["project_ids"]), 1)

    def test_team_list_includes_owners_of_projects_the_user_joins(self):
        teammate = User.objects.create_user(
            username="teammate-owner@example.com",
            email="teammate-owner@example.com",
            password="Testing-123!",
        )
        shared_project = Project.objects.create(name="Partner work", owner=teammate)
        shared_project.members.add(self.user)
        response = self.client.get("/api/team/")
        teammate_entry = next(item for item in response.data if item["id"] == teammate.id)
        self.assertEqual(teammate_entry["project_ids"], [shared_project.id])

    def test_prediction_validation_and_model_response(self):
        invalid = self.client.post(
            "/api/predictions/priority/",
            {"description": "urgent task", "task_type": "invalid"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)

        priority = self.client.post(
            "/api/predictions/priority/",
            {"description": "Improve the release workflow", "task_type": "improvement"},
            format="json",
        )
        self.assertEqual(priority.status_code, 200, priority.data)
        self.assertIn(priority.data["priority"], ["low", "medium", "high", "critical"])

        response = self.client.post(
            "/api/predictions/completion/",
            {"complexity": 4, "effort_points": 8, "team_size": 2, "dependencies": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertGreater(response.data["estimated_days"], 0)
        self.assertEqual(response.data["training_data"], "synthetic")

        delay = self.client.post(
            "/api/predictions/delay/",
            {"progress": 35, "completed": 2, "pending": 6, "days_until_deadline": 8},
            format="json",
        )
        self.assertEqual(delay.status_code, 200, delay.data)
        self.assertIn(delay.data["forecast"], ["on_time", "at_risk", "likely_delayed"])

    def test_prediction_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/predictions/delay/", {"progress": 20}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    @patch("core.ml.priority_model", side_effect=FileNotFoundError("priority weights missing"))
    def test_missing_model_artifact_returns_actionable_service_error(self, _model):
        response = self.client.post(
            "/api/predictions/priority/",
            {"description": "Review the release notes", "task_type": "other"},
            format="json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "model_not_trained")
