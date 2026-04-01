"""
GitLab service – repository linking, CI/CD pipeline management, webhook registration.
Uses the python-gitlab SDK.
"""
import logging
from typing import Optional
import gitlab
from gitlab.exceptions import GitlabGetError, GitlabCreateError

from app.core.config import settings

logger = logging.getLogger(__name__)


class GitLabService:
    def __init__(self):
        self.gl = gitlab.Gitlab(
            url=settings.GITLAB_URL,
            private_token=settings.GITLAB_TOKEN,
        )

    # ── Repository ─────────────────────────────

    def get_project(self, project_id_or_path: str):
        """Fetch a GitLab project by ID or URL-encoded path."""
        try:
            return self.gl.projects.get(project_id_or_path)
        except GitlabGetError as e:
            logger.error(f"GitLab get_project error: {e}")
            return None

    def list_branches(self, project_id: str) -> list[dict]:
        project = self.get_project(project_id)
        if not project:
            return []
        return [{"name": b.name, "commit": b.commit["id"]} for b in project.branches.list()]

    # ── CI/CD Variables ─────────────────────────

    def set_ci_variable(self, project_id: str, key: str, value: str, masked: bool = False):
        """Set or update a CI/CD variable in the GitLab project."""
        project = self.get_project(project_id)
        if not project:
            return None
        try:
            var = project.variables.get(key)
            var.value = value
            var.masked = masked
            var.save()
        except GitlabGetError:
            project.variables.create({"key": key, "value": value, "masked": masked})

    def provision_ecr_variables(
        self,
        project_id: str,
        ecr_registry: str,
        ecr_repo_name: str,
        aws_region: str,
    ):
        """Push ECR-related variables needed by .gitlab-ci.yml."""
        vars_to_set = {
            "ECR_REGISTRY": ecr_registry,
            "ECR_REPOSITORY": ecr_repo_name,
            "AWS_DEFAULT_REGION": aws_region,
        }
        for key, value in vars_to_set.items():
            self.set_ci_variable(project_id, key, value)
        logger.info(f"Provisioned ECR CI variables for GitLab project {project_id}")

    # ── Webhooks ────────────────────────────────

    def create_push_webhook(self, project_id: str, webhook_url: str) -> Optional[dict]:
        """Register a push-event webhook pointing to our backend."""
        project = self.get_project(project_id)
        if not project:
            return None
        try:
            hook = project.hooks.create({
                "url": webhook_url,
                "push_events": True,
                "pipeline_events": True,
                "token": settings.GITLAB_WEBHOOK_SECRET,
                "enable_ssl_verification": True,
            })
            return {"id": hook.id, "url": hook.url}
        except GitlabCreateError as e:
            logger.error(f"GitLab create_webhook error: {e}")
            return None

    def list_webhooks(self, project_id: str) -> list[dict]:
        project = self.get_project(project_id)
        if not project:
            return []
        return [{"id": h.id, "url": h.url} for h in project.hooks.list()]

    # ── Pipeline ────────────────────────────────

    def trigger_pipeline(self, project_id: str, ref: str = "main", variables: dict = {}) -> Optional[dict]:
        """Manually kick off a GitLab pipeline."""
        project = self.get_project(project_id)
        if not project:
            return None
        pipeline = project.pipelines.create({
            "ref": ref,
            "variables": [{"key": k, "value": v} for k, v in variables.items()],
        })
        return {"id": pipeline.id, "status": pipeline.status, "web_url": pipeline.web_url}

    def get_pipeline_status(self, project_id: str, pipeline_id: str) -> Optional[dict]:
        project = self.get_project(project_id)
        if not project:
            return None
        pipeline = project.pipelines.get(pipeline_id)
        return {"id": pipeline.id, "status": pipeline.status, "duration": pipeline.duration}

    # ── .gitlab-ci.yml template ─────────────────

    def generate_ci_template(
        self,
        ecr_registry: str,
        ecr_repo: str,
        region: str = "us-east-1",
        branch: str = "main",
        dockerfile: str = "Dockerfile",
    ) -> str:
        """Return a ready-to-commit .gitlab-ci.yml for Docker → ECR pipeline."""
        return f"""
stages:
  - build
  - push

variables:
  IMAGE_TAG: $CI_COMMIT_SHORT_SHA
  ECR_IMAGE: {ecr_registry}/{ecr_repo}:$IMAGE_TAG

build_image:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  before_script:
    - apk add --no-cache aws-cli
    - aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {ecr_registry}
  script:
    - docker build -f {dockerfile} -t $ECR_IMAGE .
  only:
    - {branch}

push_image:
  stage: push
  image: docker:24
  services:
    - docker:24-dind
  before_script:
    - apk add --no-cache aws-cli
    - aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {ecr_registry}
  script:
    - docker push $ECR_IMAGE
  only:
    - {branch}
  needs:
    - build_image
""".strip()


gitlab_service = GitLabService()