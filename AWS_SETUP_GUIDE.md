# AWS Event-Driven ECS Deployment Without Terraform

This setup removes Terraform from the deployment pipeline.

Your flow becomes:

```text
backend creates/reuses ECR repository
-> backend builds Docker image
-> backend pushes image to ECR
-> EventBridge detects successful ECR push
-> Lambda creates or updates ECS service
-> ALB exposes the app publicly
```

Terraform is not required for image deployment. You only need to create the shared AWS resources once using the AWS Console or AWS CLI.

## File Structure

```text
AWS_SETUP_GUIDE.md
aws/
  lambda/
    ecr-to-ecs-deploy/
      index.js
      package.json
      README.md
  setup/
    ecs-task-trust-policy.json
    lambda-trust-policy.json
    lambda-policy.json
    lambda-environment.json
    ecr-push-event-pattern.json
    eventbridge-targets.json
```

## Architecture

ECR emits an EventBridge event when an image push completes successfully.

EventBridge invokes Lambda. Lambda reads:

- `detail.repository-name`
- `detail.image-tag`

Then Lambda constructs:

```text
<account-id>.dkr.ecr.<region>.amazonaws.com/<repository-name>:<image-tag>
```

For the first push to a repository, Lambda creates:

- ECS task definition
- ALB target group
- ALB listener rule
- ECS Fargate service

For later pushes to the same repository, Lambda:

- registers a new task definition revision
- updates the ECS service
- forces a new deployment

ECS replaces tasks automatically during the rolling deployment.

If `BACKEND_CALLBACK_URL` is configured on Lambda, Lambda also calls your backend after the AWS deployment step and saves the public URL in your database.

## Section 1: Prerequisites

Install on your PC:

- AWS CLI v2
- Docker
- Node.js 20+
- npm

Terraform is not needed.

Verify AWS credentials:

```powershell
aws sts get-caller-identity
```

## Section 2: AWS Setup Steps

You need to create shared AWS resources once.

### 1. Create Or Use A VPC

You can use the default VPC for the first version.

Get default VPC:

```powershell
$AWS_REGION = "us-east-1"
$VPC_ID = aws ec2 describe-vpcs `
  --filters "Name=is-default,Values=true" `
  --query "Vpcs[0].VpcId" `
  --output text `
  --region $AWS_REGION
```

Get public subnets:

```powershell
$SUBNET_IDS = aws ec2 describe-subnets `
  --filters "Name=vpc-id,Values=$VPC_ID" `
  --query "Subnets[*].SubnetId" `
  --output text `
  --region $AWS_REGION
```

### 2. Create ECS Cluster

```powershell
$PROJECT_NAME = "hybrid-paas"

aws ecs create-cluster `
  --cluster-name "$PROJECT_NAME-cluster" `
  --region $AWS_REGION
```

### 3. Create Security Groups

Create ALB security group:

```powershell
$ALB_SG_ID = aws ec2 create-security-group `
  --group-name "$PROJECT_NAME-alb-sg" `
  --description "Public HTTP access to ALB" `
  --vpc-id $VPC_ID `
  --query "GroupId" `
  --output text `
  --region $AWS_REGION

aws ec2 authorize-security-group-ingress `
  --group-id $ALB_SG_ID `
  --protocol tcp `
  --port 80 `
  --cidr 0.0.0.0/0 `
  --region $AWS_REGION
```

Create ECS task security group:

```powershell
$ECS_SG_ID = aws ec2 create-security-group `
  --group-name "$PROJECT_NAME-ecs-tasks-sg" `
  --description "Allow ALB to reach ECS tasks" `
  --vpc-id $VPC_ID `
  --query "GroupId" `
  --output text `
  --region $AWS_REGION

aws ec2 authorize-security-group-ingress `
  --group-id $ECS_SG_ID `
  --protocol tcp `
  --port 3000 `
  --source-group $ALB_SG_ID `
  --region $AWS_REGION
```

### 4. Create Internet-Facing ALB

```powershell
$ALB_ARN = aws elbv2 create-load-balancer `
  --name "$PROJECT_NAME-alb" `
  --type application `
  --scheme internet-facing `
  --security-groups $ALB_SG_ID `
  --subnets $SUBNET_IDS.Split(" ") `
  --query "LoadBalancers[0].LoadBalancerArn" `
  --output text `
  --region $AWS_REGION
```

Get ALB DNS:

```powershell
$ALB_DNS_NAME = aws elbv2 describe-load-balancers `
  --load-balancer-arns $ALB_ARN `
  --query "LoadBalancers[0].DNSName" `
  --output text `
  --region $AWS_REGION
```

Create HTTP listener:

```powershell
$ALB_LISTENER_ARN = aws elbv2 create-listener `
  --load-balancer-arn $ALB_ARN `
  --protocol HTTP `
  --port 80 `
  --default-actions Type=fixed-response,FixedResponseConfig="{StatusCode=404,ContentType=text/plain,MessageBody='No deployment route matched this request.'}" `
  --query "Listeners[0].ListenerArn" `
  --output text `
  --region $AWS_REGION
```

### 5. Create CloudWatch Log Group For ECS Tasks

```powershell
aws logs create-log-group `
  --log-group-name "/ecs/$PROJECT_NAME" `
  --region $AWS_REGION
```

### 6. Create ECS Task Execution Role

Create `ecs-task-trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Create role:

```powershell
aws iam create-role `
  --role-name "$PROJECT_NAME-ecs-task-execution-role" `
  --assume-role-policy-document file://ecs-task-trust-policy.json

aws iam attach-role-policy `
  --role-name "$PROJECT_NAME-ecs-task-execution-role" `
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

Create app task role:

```powershell
aws iam create-role `
  --role-name "$PROJECT_NAME-ecs-task-role" `
  --assume-role-policy-document file://ecs-task-trust-policy.json
```

Get role ARNs:

```powershell
$ECS_TASK_EXECUTION_ROLE = aws iam get-role `
  --role-name "$PROJECT_NAME-ecs-task-execution-role" `
  --query "Role.Arn" `
  --output text

$ECS_TASK_ROLE = aws iam get-role `
  --role-name "$PROJECT_NAME-ecs-task-role" `
  --query "Role.Arn" `
  --output text
```

### 7. Create Lambda IAM Role

Create `lambda-trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Create role:

```powershell
aws iam create-role `
  --role-name "$PROJECT_NAME-ecr-ecs-deployer-role" `
  --assume-role-policy-document file://lambda-trust-policy.json
```

Create `lambda-policy.json`. Replace account ID and region if needed:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecs:CreateService",
        "ecs:DescribeServices",
        "ecs:RegisterTaskDefinition",
        "ecs:UpdateService",
        "ecs:TagResource"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:CreateRule",
        "elasticloadbalancing:CreateTargetGroup",
        "elasticloadbalancing:DescribeRules",
        "elasticloadbalancing:DescribeTargetGroups",
        "elasticloadbalancing:ModifyTargetGroupAttributes",
        "elasticloadbalancing:AddTags"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::<account-id>:role/hybrid-paas-ecs-task-execution-role",
        "arn:aws:iam::<account-id>:role/hybrid-paas-ecs-task-role"
      ],
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": "ecs-tasks.amazonaws.com"
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": "iam:CreateServiceLinkedRole",
      "Resource": "arn:aws:iam::<account-id>:role/aws-service-role/ecs.amazonaws.com/AWSServiceRoleForECS",
      "Condition": {
        "StringEquals": {
          "iam:AWSServiceName": "ecs.amazonaws.com"
        }
      }
    }
  ]
}
```

Attach policy:

```powershell
aws iam put-role-policy `
  --role-name "$PROJECT_NAME-ecr-ecs-deployer-role" `
  --policy-name "$PROJECT_NAME-ecr-ecs-deployer-policy" `
  --policy-document file://lambda-policy.json
```

Get Lambda role ARN:

```powershell
$LAMBDA_ROLE_ARN = aws iam get-role `
  --role-name "$PROJECT_NAME-ecr-ecs-deployer-role" `
  --query "Role.Arn" `
  --output text
```

### 8. Package And Create Lambda

From the repo root:

```powershell
cd aws/lambda/ecr-to-ecs-deploy
npm install --omit=dev
Compress-Archive -Path * -DestinationPath function.zip -Force
```

Create Lambda:

```powershell
$AWS_ACCOUNT_ID = aws sts get-caller-identity --query "Account" --output text

aws lambda create-function `
  --function-name "$PROJECT_NAME-ecr-to-ecs-deploy" `
  --runtime nodejs20.x `
  --handler index.handler `
  --role $LAMBDA_ROLE_ARN `
  --zip-file fileb://function.zip `
  --timeout 60 `
  --memory-size 256 `
  --environment "Variables={AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID,PROJECT_NAME=$PROJECT_NAME,ECR_REPOSITORY_PREFIX=hybrid-paas/,ECS_CLUSTER_NAME=$PROJECT_NAME-cluster,ECS_TASK_EXECUTION_ROLE=$ECS_TASK_EXECUTION_ROLE,ECS_TASK_ROLE=$ECS_TASK_ROLE,ECS_SECURITY_GROUP_IDS=$ECS_SG_ID,ECS_SUBNET_IDS=$($SUBNET_IDS -replace ' ',','),ASSIGN_PUBLIC_IP=ENABLED,ALB_LISTENER_ARN=$ALB_LISTENER_ARN,ALB_DNS_NAME=$ALB_DNS_NAME,VPC_ID=$VPC_ID,PUBLIC_DOMAIN_NAME=,CONTAINER_NAME=app,CONTAINER_PORT=3000,DESIRED_COUNT=1,TASK_CPU=512,TASK_MEMORY=1024,HEALTH_CHECK_PATH=/,ECS_LOG_GROUP=/ecs/$PROJECT_NAME,APP_ENVIRONMENT_JSON={},BACKEND_CALLBACK_URL=,BACKEND_CALLBACK_SECRET=}" `
  --region $AWS_REGION
```

To save the deployed URL in your DB, set these Lambda variables after your backend has a public URL:

```text
BACKEND_CALLBACK_URL=https://your-public-backend-domain.com/deployments/aws-callback
BACKEND_CALLBACK_SECRET=<same value as AWS_DEPLOY_CALLBACK_SECRET in server/.env>
```

AWS Lambda cannot call `http://localhost:8000` on your laptop. Your backend must be reachable from AWS.

If you later edit Lambda code:

```powershell
Compress-Archive -Path * -DestinationPath function.zip -Force

aws lambda update-function-code `
  --function-name "$PROJECT_NAME-ecr-to-ecs-deploy" `
  --zip-file fileb://function.zip `
  --region $AWS_REGION
```

### 9. Create EventBridge Rule

Event pattern for all successful pushes under `hybrid-paas/`:

```json
{
  "source": ["aws.ecr"],
  "detail-type": ["ECR Image Action"],
  "detail": {
    "action-type": ["PUSH"],
    "result": ["SUCCESS"],
    "repository-name": [
      {
        "prefix": "hybrid-paas/"
      }
    ]
  }
}
```

Create `event-pattern.json` with the above content.

Create rule:

```powershell
aws events put-rule `
  --name "$PROJECT_NAME-ecr-push" `
  --event-pattern file://event-pattern.json `
  --region $AWS_REGION
```

Allow EventBridge to invoke Lambda:

```powershell
$RULE_ARN = aws events describe-rule `
  --name "$PROJECT_NAME-ecr-push" `
  --query "Arn" `
  --output text `
  --region $AWS_REGION

aws lambda add-permission `
  --function-name "$PROJECT_NAME-ecr-to-ecs-deploy" `
  --statement-id AllowExecutionFromEventBridge `
  --action lambda:InvokeFunction `
  --principal events.amazonaws.com `
  --source-arn $RULE_ARN `
  --region $AWS_REGION
```

Connect rule to Lambda:

```powershell
$LAMBDA_ARN = aws lambda get-function `
  --function-name "$PROJECT_NAME-ecr-to-ecs-deploy" `
  --query "Configuration.FunctionArn" `
  --output text `
  --region $AWS_REGION

aws events put-targets `
  --rule "$PROJECT_NAME-ecr-push" `
  --targets "Id"="1","Arn"="$LAMBDA_ARN" `
  --region $AWS_REGION
```

### 10. Optional Domain Setup

Without a domain, Lambda uses path-based routing:

```text
http://<alb-dns-name>/<generated-app-slug>
```

For a Vercel-like setup, use wildcard DNS:

```text
*.apps.example.com -> ALB DNS name
```

Then update Lambda env:

```powershell
aws lambda update-function-configuration `
  --function-name "$PROJECT_NAME-ecr-to-ecs-deploy" `
  --environment "Variables={PUBLIC_DOMAIN_NAME=apps.example.com,...other existing variables...}" `
  --region $AWS_REGION
```

With a domain, Lambda creates host-based routes:

```text
http://hybrid-paas-user-repo.apps.example.com
```

## Section 3: Testing

Push a new image to a matching ECR repository:

```text
hybrid-paas/<owner>/<repo>:latest
```

Watch Lambda logs:

```powershell
aws logs tail "/aws/lambda/hybrid-paas-ecr-to-ecs-deploy" --follow --region us-east-1
```

If the backend callback is configured, the frontend deployments page will update automatically with:

- status `deployed`
- public URL
- ECS service name

List ECS services:

```powershell
aws ecs list-services `
  --cluster hybrid-paas-cluster `
  --region us-east-1
```

Describe a service:

```powershell
aws ecs describe-services `
  --cluster hybrid-paas-cluster `
  --services <generated-service-name> `
  --region us-east-1
```

Check target health:

```powershell
aws elbv2 describe-target-health `
  --target-group-arn <target-group-arn> `
  --region us-east-1
```

## Section 4: Troubleshooting

### Image Push Does Not Trigger Lambda

- Confirm the repository starts with `hybrid-paas/`.
- Confirm the EventBridge rule exists.
- Confirm EventBridge target is the Lambda function.
- Confirm Lambda permission allows `events.amazonaws.com`.

### Lambda Permission Error

Check Lambda role permissions for:

- `ecs:CreateService`
- `ecs:RegisterTaskDefinition`
- `ecs:UpdateService`
- `elasticloadbalancing:CreateTargetGroup`
- `elasticloadbalancing:CreateRule`
- `iam:PassRole`
- CloudWatch Logs

### ECS Task Fails To Start

- Confirm the image exists in ECR.
- Confirm ECS task execution role can pull from ECR.
- Confirm the app listens on `0.0.0.0`.
- Confirm the app uses the same port as `CONTAINER_PORT`.

### ALB Shows 404

- You are hitting the ALB root path.
- Use the route printed in Lambda logs.
- Without a domain, routes are path-based.

### Target Group Is Unhealthy

- Check ECS task logs in `/ecs/hybrid-paas`.
- Confirm `HEALTH_CHECK_PATH` returns HTTP `200-399`.
- Confirm security group allows ALB -> ECS task port.

## Final Behavior

After this setup, your backend only needs to push Docker images to ECR.

No Terraform.
No manual ECS service creation.
No manual deploy button.

The deployment happens automatically from:

```text
ECR push -> EventBridge -> Lambda -> ECS -> ALB
```

The simple frontend integration is:

```text
Lambda -> backend callback -> deployment row updated -> frontend polls /deployments
```

## References

- Amazon ECR EventBridge events: https://docs.aws.amazon.com/AmazonECR/latest/userguide/ecr-eventbridge.html
- ECS rolling deployments: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-type-ecs.html
