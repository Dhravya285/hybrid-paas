"""
AWS service wrapper – ECR, ECS, Lambda, EventBridge
All boto3 calls are async-friendly via run_in_executor.
"""
import json
import logging
from typing import Optional
import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _boto_client(service: str):
    return boto3.client(
        service,
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


# ──────────────────────────────────────────
# ECR
# ──────────────────────────────────────────

class ECRService:
    def __init__(self):
        self.client = _boto_client("ecr")

    def create_repository(self, name: str) -> dict:
        """Create an ECR repository for a project."""
        try:
            resp = self.client.create_repository(
                repositoryName=name,
                imageScanningConfiguration={"scanOnPush": True},
                imageTagMutability="MUTABLE",
            )
            return resp["repository"]
        except self.client.exceptions.RepositoryAlreadyExistsException:
            resp = self.client.describe_repositories(repositoryNames=[name])
            return resp["repositories"][0]

    def delete_repository(self, name: str) -> bool:
        try:
            self.client.delete_repository(repositoryName=name, force=True)
            return True
        except ClientError as e:
            logger.error(f"ECR delete_repository error: {e}")
            return False

    def list_images(self, repo_name: str) -> list:
        resp = self.client.list_images(repositoryName=repo_name)
        return resp.get("imageIds", [])

    def get_authorization_token(self) -> dict:
        resp = self.client.get_authorization_token()
        return resp["authorizationData"][0]


# ──────────────────────────────────────────
# ECS
# ──────────────────────────────────────────

class ECSService:
    def __init__(self):
        self.client = _boto_client("ecs")

    def register_task_definition(
        self,
        family: str,
        image_uri: str,
        cpu: str,
        memory: str,
        port: int,
        env_vars: list[dict],
        execution_role_arn: str,
    ) -> dict:
        resp = self.client.register_task_definition(
            family=family,
            networkMode="awsvpc",
            requiresCompatibilities=["FARGATE"],
            cpu=cpu,
            memory=memory,
            executionRoleArn=execution_role_arn,
            containerDefinitions=[
                {
                    "name": family,
                    "image": image_uri,
                    "portMappings": [{"containerPort": port, "protocol": "tcp"}],
                    "environment": env_vars,
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": f"/ecs/{family}",
                            "awslogs-region": settings.AWS_REGION,
                            "awslogs-stream-prefix": "ecs",
                        },
                    },
                }
            ],
        )
        return resp["taskDefinition"]

    def update_service(
        self,
        cluster: str,
        service_name: str,
        task_definition_arn: str,
        desired_count: int = 1,
    ) -> dict:
        resp = self.client.update_service(
            cluster=cluster,
            service=service_name,
            taskDefinition=task_definition_arn,
            desiredCount=desired_count,
            forceNewDeployment=True,
        )
        return resp["service"]

    def create_service(
        self,
        cluster: str,
        service_name: str,
        task_definition_arn: str,
        subnet_ids: list[str],
        security_group_ids: list[str],
        desired_count: int = 1,
    ) -> dict:
        resp = self.client.create_service(
            cluster=cluster,
            serviceName=service_name,
            taskDefinition=task_definition_arn,
            desiredCount=desired_count,
            launchType="FARGATE",
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": subnet_ids,
                    "securityGroups": security_group_ids,
                    "assignPublicIp": "ENABLED",
                }
            },
            deploymentConfiguration={
                "maximumPercent": 200,
                "minimumHealthyPercent": 100,
            },
        )
        return resp["service"]

    def describe_service(self, cluster: str, service_name: str) -> Optional[dict]:
        try:
            resp = self.client.describe_services(cluster=cluster, services=[service_name])
            services = resp.get("services", [])
            return services[0] if services else None
        except ClientError as e:
            logger.error(f"ECS describe_service error: {e}")
            return None

    def list_tasks(self, cluster: str, service_name: str) -> list:
        resp = self.client.list_tasks(cluster=cluster, serviceName=service_name)
        return resp.get("taskArns", [])


# ──────────────────────────────────────────
# Lambda
# ──────────────────────────────────────────

class LambdaService:
    def __init__(self):
        self.client = _boto_client("lambda")

    def invoke_deployer(self, payload: dict) -> dict:
        """Invoke the ECS deployer Lambda function."""
        resp = self.client.invoke(
            FunctionName=settings.LAMBDA_DEPLOY_FUNCTION,
            InvocationType="Event",           # async invocation
            Payload=json.dumps(payload).encode(),
        )
        return {"status_code": resp["StatusCode"]}


# ──────────────────────────────────────────
# EventBridge
# ──────────────────────────────────────────

class EventBridgeService:
    def __init__(self):
        self.client = _boto_client("events")

    def put_rule(self, rule_name: str, ecr_repo_arn: str) -> str:
        """Create an EventBridge rule that fires on ECR image pushes."""
        event_pattern = json.dumps({
            "source": ["aws.ecr"],
            "detail-type": ["ECR Image Action"],
            "detail": {
                "action-type": ["PUSH"],
                "result": ["SUCCESS"],
                "repository-name": [ecr_repo_arn.split("/")[-1]],
            },
        })
        resp = self.client.put_rule(
            Name=rule_name,
            EventPattern=event_pattern,
            State="ENABLED",
            EventBusName=settings.EVENTBRIDGE_BUS_NAME,
        )
        return resp["RuleArn"]

    def put_lambda_target(self, rule_name: str, lambda_arn: str) -> bool:
        resp = self.client.put_targets(
            Rule=rule_name,
            EventBusName=settings.EVENTBRIDGE_BUS_NAME,
            Targets=[{"Id": "ecs-deployer-lambda", "Arn": lambda_arn}],
        )
        return resp["FailedEntryCount"] == 0


# ──────────────────────────────────────────
# Singletons
# ──────────────────────────────────────────

ecr_service       = ECRService()
ecs_service       = ECSService()
lambda_service    = LambdaService()
eventbridge_service = EventBridgeService()