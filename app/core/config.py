from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    PROJECT_NAME: str = "HybridPaaS"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    ALGORITHM: str = "HS256"

    # CORS / Hosts
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "https://yourdomain.com"]
    ALLOWED_HOSTS: List[str] = ["*"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/paasdb"

    # AWS
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    ECR_REGISTRY_URL: str = ""           # e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com
    ECS_CLUSTER_NAME: str = "paas-cluster"
    ECS_TASK_EXECUTION_ROLE_ARN: str = ""
    LAMBDA_DEPLOY_FUNCTION: str = "paas-ecs-deployer"
    EVENTBRIDGE_BUS_NAME: str = "paas-events"

    # GitLab
    GITLAB_URL: str = "https://gitlab.com"
    GITLAB_TOKEN: str = ""               # personal / group / project access token
    GITLAB_WEBHOOK_SECRET: str = "change-me"

    # CloudFormation / Terraform state
    TERRAFORM_STATE_BUCKET: str = "paas-tf-state"
    CF_STACK_PREFIX: str = "paas"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()