import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Generator

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config.db import get_db
from models.deployments import Deployment
from models.users import User

router = APIRouter()
DEFAULT_ECR_REPOSITORY_URI = os.getenv("DEFAULT_ECR_REPOSITORY_URI", "").strip()

ECR_URI_PATTERN = re.compile(
    r"^(?P<registry>\d+\.dkr\.ecr\.(?P<region>[a-z0-9-]+)\.amazonaws\.com)"
    r"/(?P<repository>[A-Za-z0-9._/\-]+)$"
)


class DeployRequest(BaseModel):
    owner: str
    repo: str
    branch: str
    source_dir: str = "/"
    build_command: str | None = None
    run_command: str | None = None
    ecr_repository_uri: str | None = None
    image_tag: str = Field(default="latest", min_length=1)
    aws_region: str | None = None


class DeployError(Exception):
    pass


def emit(payload: dict) -> str:
    return json.dumps(payload) + "\n"


def log_payload(message: str, *, level: str = "info") -> str:
    return emit({"type": "log", "level": level, "message": message})


def ensure_command(name: str) -> None:
    if shutil.which(name):
        return
    raise DeployError(f"Required command not found in PATH: {name}")


def ensure_docker_ready() -> None:
    result = run_captured(["docker", "info"])
    if result.returncode == 0:
        return

    details = (result.stderr or result.stdout).strip()
    if "dockerDesktopLinuxEngine" in details or "docker_engine" in details:
        raise DeployError(
            "Docker daemon is not running. Start Docker Desktop and make sure the Linux "
            "container engine is available, then retry deploy."
        )

    raise DeployError(f"Docker is installed but not ready: {details or 'docker info failed'}")


def parse_ecr_uri(repository_uri: str, aws_region: str | None) -> tuple[str, str, str]:
    match = ECR_URI_PATTERN.match(repository_uri.strip())
    if not match:
        raise DeployError(
            "Invalid ECR repository URI. Expected format: "
            "123456789012.dkr.ecr.ap-south-1.amazonaws.com/my-service"
        )

    registry = match.group("registry")
    repository = match.group("repository")
    region = aws_region or match.group("region")
    return registry, repository, region


def resolve_ecr_repository_uri(repository_uri: str | None) -> str:
    resolved = (repository_uri or DEFAULT_ECR_REPOSITORY_URI).strip()
    if not resolved:
        raise DeployError(
            "No ECR repository configured. Set DEFAULT_ECR_REPOSITORY_URI on the backend "
            "or send ecr_repository_uri in the deploy request."
        )
    return resolved


def sanitize_repository_segment(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-.")
    if not sanitized:
        raise DeployError(f"Invalid repository segment: {value!r}")
    return sanitized


def build_project_repository_uri(base_repository_uri: str, owner: str, repo: str) -> str:
    registry, base_repository, _ = parse_ecr_uri(base_repository_uri, None)
    owner_segment = sanitize_repository_segment(owner)
    repo_segment = sanitize_repository_segment(repo)
    return f"{registry}/{base_repository}/{owner_segment}/{repo_segment}"


def sanitize_image_tag(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-.")
    if not sanitized:
        raise DeployError(f"Invalid image tag: {value!r}")
    return sanitized[:120]


def resolve_image_tag(image_tag: str | None, branch: str) -> str:
    requested = (image_tag or "").strip()
    if requested and requested.lower() != "latest":
        return sanitize_image_tag(requested)

    branch_segment = sanitize_image_tag(branch)[:60]
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{branch_segment}-{timestamp}"


def build_local_image_name(repository_name: str, image_tag: str) -> str:
    local_name = repository_name.replace("/", "-").lower() or "hybrid-paas"
    return f"{local_name}:{image_tag}"


def resolve_source_dir(repo_root: Path, source_dir: str) -> Path:
    normalized = source_dir.strip() or "/"
    relative = normalized.strip("/")
    target = (repo_root / relative).resolve() if relative else repo_root.resolve()
    repo_root_resolved = repo_root.resolve()

    try:
        target.relative_to(repo_root_resolved)
    except ValueError as exc:
        raise DeployError("Selected source directory escapes the cloned repository") from exc

    if not target.exists():
        raise DeployError(f"Source directory does not exist: {normalized}")

    if not target.is_dir():
        raise DeployError(f"Selected source path is not a directory: {normalized}")

    return target


def detect_runtime(source_dir: Path) -> str:
    package_json = source_dir / "package.json"
    if not package_json.exists():
        raise DeployError("Next.js deploy requires a package.json in the selected source folder")

    try:
        package_data = json.loads(package_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeployError("Could not parse package.json in the selected source folder") from exc

    dependencies = package_data.get("dependencies", {})
    dev_dependencies = package_data.get("devDependencies", {})

    if "next" in dependencies or "next" in dev_dependencies:
        return "nextjs"

    if (
        (source_dir / "next.config.js").exists()
        or (source_dir / "next.config.mjs").exists()
        or (source_dir / "next.config.ts").exists()
    ):
        return "nextjs"

    raise DeployError("Selected source folder is not a Next.js app")


def render_nextjs_dockerfile(build_command: str | None, run_command: str | None) -> str:
    lines = [
        "FROM node:20-alpine",
        "WORKDIR /app",
        "COPY package*.json ./",
        'RUN ["sh", "-lc", "if [ -f package-lock.json ]; then npm ci; else npm install; fi"]',
        "COPY . .",
    ]

    if build_command and build_command.strip():
        lines.append(f'RUN ["sh", "-lc", {json.dumps(build_command.strip())}]')

    run_value = (run_command or "npm start").strip()
    lines.extend(
        [
            "EXPOSE 3000",
            f'CMD ["sh", "-lc", {json.dumps(run_value)}]',
        ]
    )
    return "\n".join(lines) + "\n"


def ensure_dockerfile(
    source_dir: Path, build_command: str | None, run_command: str | None
) -> tuple[Path, bool]:
    existing = source_dir / "Dockerfile"
    if existing.exists():
        return existing, False

    runtime = detect_runtime(source_dir)
    generated = source_dir / ".generated.Dockerfile"

    if runtime != "nextjs":
        raise DeployError("Only Next.js source folders are supported")

    generated.write_text(render_nextjs_dockerfile(build_command, run_command), encoding="utf-8")
    return generated, True


def read_base_image(dockerfile_path: Path) -> str | None:
    try:
        lines = dockerfile_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.upper().startswith("FROM "):
            continue

        remainder = line[5:].strip()
        if not remainder:
            return None

        image = remainder.split(" AS ", 1)[0].split(" as ", 1)[0].strip()
        if image.startswith("--"):
            parts = image.split()
            if len(parts) >= 2:
                image = parts[-1]
        return image or None

    return None


def is_transient_registry_error(message: str) -> bool:
    lowered = message.lower()
    transient_markers = (
        "tls handshake timeout",
        "i/o timeout",
        "context deadline exceeded",
        "temporary failure",
        "connection reset by peer",
        "eof",
        "net/http",
        "failed to do request",
    )
    return any(marker in lowered for marker in transient_markers)


def pull_base_image_with_retries(image: str, attempts: int = 3, delay_seconds: int = 5) -> Generator[str, None, None]:
    last_error = ""
    for attempt in range(1, attempts + 1):
        yield log_payload(f"Pulling base image {image} (attempt {attempt}/{attempts})")
        result = run_captured(["docker", "pull", image])
        if result.returncode == 0:
            output = (result.stdout or "").strip()
            if output:
                for line in output.splitlines():
                    if line.strip():
                        yield log_payload(line.strip())
            return

        details = (result.stderr or result.stdout).strip()
        last_error = details or f"docker pull failed for {image}"

        if attempt >= attempts or not is_transient_registry_error(last_error):
            raise DeployError(f"Failed to pull base image {image}: {last_error}")

        yield log_payload(
            f"Transient registry error while pulling {image}. Retrying in {delay_seconds}s...",
            level="warning",
        )
        time.sleep(delay_seconds)


def stream_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    redact_values: list[str] | None = None,
    stdin_text: str | None = None,
) -> Generator[str, None, None]:
    process = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE if stdin_text is not None else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    if stdin_text is not None and process.stdin:
        process.stdin.write(stdin_text)
        process.stdin.close()

    if process.stdout:
        for raw_line in process.stdout:
            line = raw_line.rstrip()
            if not line:
                continue
            if redact_values:
                for value in redact_values:
                    if value:
                        line = line.replace(value, "***")
            yield log_payload(line)

    return_code = process.wait()
    if return_code != 0:
        raise DeployError(
            f"Command failed with exit code {return_code}: {subprocess.list2cmdline(command)}"
        )


def run_captured(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def get_authenticated_user(request: Request, db: Session) -> User:
    user_id = request.state.user_id
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


def serialize_deployment(deployment: Deployment) -> dict:
    return {
        "id": deployment.id,
        "owner": deployment.owner,
        "repo": deployment.repo,
        "branch": deployment.branch,
        "source_dir": deployment.source_dir,
        "repository_uri": deployment.repository_uri,
        "image_tag": deployment.image_tag,
        "image_uri": deployment.image_uri,
        "status": deployment.status,
        "error_message": deployment.error_message,
        "created_at": deployment.created_at.isoformat() if deployment.created_at else None,
        "updated_at": deployment.updated_at.isoformat() if deployment.updated_at else None,
    }


@router.get("/repos")
async def get_repos(request: Request, db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)

    response = requests.get(
        "https://api.github.com/user/repos?per_page=100&sort=updated&direction=desc",
        headers={"Authorization": f"Bearer {user.github_access_token}"},
        timeout=30,
    )

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()


@router.get("/deployments")
async def get_deployments(request: Request, db: Session = Depends(get_db)):
    user = get_authenticated_user(request, db)
    deployments = (
        db.query(Deployment)
        .filter(Deployment.user_id == user.id)
        .order_by(Deployment.created_at.desc(), Deployment.id.desc())
        .all()
    )
    return [serialize_deployment(deployment) for deployment in deployments]


@router.post("/deploy/stream")
async def deploy_repo(
    body: DeployRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    user = get_authenticated_user(request, db)

    def generate() -> Generator[str, None, None]:
        temp_dir = Path(tempfile.mkdtemp(prefix="hybrid-paas-deploy-"))
        repo_root = temp_dir / body.repo
        safe_clone_url = f"https://github.com/{body.owner}/{body.repo}.git"
        clone_url = (
            f"https://x-access-token:{user.github_access_token}@github.com/"
            f"{body.owner}/{body.repo}.git"
        )
        deployment: Deployment | None = None

        try:
            yield emit({"type": "status", "status": "running"})
            yield log_payload("Starting deployment pipeline")

            for command_name in ("git", "docker", "aws"):
                ensure_command(command_name)
                yield log_payload(f"Found required command: {command_name}")

            ensure_docker_ready()
            yield log_payload("Docker daemon is reachable")

            yield log_payload(f"Cloning repository {safe_clone_url} on branch {body.branch}")
            yield from stream_command(
                ["git", "clone", "--depth", "1", "--branch", body.branch, clone_url, str(repo_root)],
                redact_values=[user.github_access_token, clone_url],
            )

            base_repository_uri = resolve_ecr_repository_uri(body.ecr_repository_uri)
            repository_uri = build_project_repository_uri(
                base_repository_uri,
                body.owner,
                body.repo,
            )
            resolved_image_tag = resolve_image_tag(body.image_tag, body.branch)
            image_uri = f"{repository_uri}:{resolved_image_tag}"

            deployment = Deployment(
                user_id=user.id,
                owner=body.owner,
                repo=body.repo,
                branch=body.branch,
                source_dir=body.source_dir,
                repository_uri=repository_uri,
                image_tag=resolved_image_tag,
                image_uri=image_uri,
                status="running",
            )
            db.add(deployment)
            db.commit()
            db.refresh(deployment)
            yield log_payload(f"Created deployment record #{deployment.id}")

            source_dir = resolve_source_dir(repo_root, body.source_dir)
            yield log_payload(f"Using source directory: {body.source_dir}")

            dockerfile_path, generated = ensure_dockerfile(
                source_dir,
                body.build_command,
                body.run_command,
            )

            if generated:
                yield log_payload(f"Generated Dockerfile at {dockerfile_path.name}")
            else:
                yield log_payload("Found existing Dockerfile in source directory")

            base_image = read_base_image(dockerfile_path)
            if base_image:
                yield from pull_base_image_with_retries(base_image)

            registry, repository_name, region = parse_ecr_uri(
                repository_uri,
                body.aws_region,
            )

            yield log_payload(f"Checking ECR repository {repository_name} in {region}")
            describe_repo = run_captured(
                [
                    "aws",
                    "ecr",
                    "describe-repositories",
                    "--repository-names",
                    repository_name,
                    "--region",
                    region,
                ]
            )

            if describe_repo.returncode != 0:
                yield log_payload("ECR repository not found, creating it")
                yield from stream_command(
                    [
                        "aws",
                        "ecr",
                        "create-repository",
                        "--repository-name",
                        repository_name,
                        "--region",
                        region,
                    ]
                )
            else:
                yield log_payload("ECR repository already exists")

            yield log_payload(f"Authenticating Docker to ECR registry {registry}")
            password_result = run_captured(
                ["aws", "ecr", "get-login-password", "--region", region]
            )
            if password_result.returncode != 0:
                raise DeployError(password_result.stderr.strip() or "Failed to fetch ECR login password")

            yield from stream_command(
                [
                    "docker",
                    "login",
                    "--username",
                    "AWS",
                    "--password-stdin",
                    registry,
                ],
                stdin_text=password_result.stdout,
            )

            local_image_name = build_local_image_name(repository_name, resolved_image_tag)

            yield log_payload(f"Building local Docker image {local_image_name}")
            yield from stream_command(
                ["docker", "build", "-f", dockerfile_path.name, "-t", local_image_name, "."],
                cwd=source_dir,
            )

            yield log_payload(f"Tagging image as {image_uri}")
            yield from stream_command(["docker", "tag", local_image_name, image_uri])

            yield log_payload(f"Pushing Docker image {image_uri}")
            yield from stream_command(["docker", "push", image_uri])

            if deployment is not None:
                deployment.status = "success"
                deployment.error_message = None
                db.add(deployment)
                db.commit()

            yield log_payload("Deployment finished successfully")
            yield emit({"type": "result", "status": "success", "image_uri": image_uri})
        except DeployError as exc:
            if deployment is not None:
                deployment.status = "error"
                deployment.error_message = str(exc)
                db.add(deployment)
                db.commit()
            yield log_payload(str(exc), level="error")
            yield emit({"type": "result", "status": "error", "message": str(exc)})
        except Exception as exc:  # pragma: no cover - defensive fallback
            message = f"Unexpected deployment error: {exc}"
            if deployment is not None:
                deployment.status = "error"
                deployment.error_message = message
                db.add(deployment)
                db.commit()
            yield log_payload(message, level="error")
            yield emit({"type": "result", "status": "error", "message": message})
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            yield log_payload("Cleaned up temporary deployment workspace")

    return StreamingResponse(generate(), media_type="application/x-ndjson")
