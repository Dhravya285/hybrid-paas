# ECR to ECS Deploy Lambda

This Lambda is triggered by EventBridge when ECR emits a successful image push event.

It extracts:

- `detail.repository-name`
- `detail.image-tag`

Then it builds the full ECR image URI.

On the first push for a repository, it creates:

- an ALB target group
- an ALB listener rule
- an ECS task definition
- an ECS service

On later pushes for the same repository, it registers a new task definition revision and calls `UpdateService` with `forceNewDeployment: true`.

If `BACKEND_CALLBACK_URL` is set, it sends deployment status and the public URL back to the backend so the frontend can show the final app URL from the database.

The AWS SDK v3 dependency is listed in `package.json`. Package this directory into `function.zip` and upload it to Lambda.
