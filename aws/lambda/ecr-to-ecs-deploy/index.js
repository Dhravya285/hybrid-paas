"use strict";

const crypto = require("crypto");
const http = require("http");
const https = require("https");
const {
  ECSClient,
  CreateServiceCommand,
  DescribeServicesCommand,
  RegisterTaskDefinitionCommand,
  UpdateServiceCommand,
} = require("@aws-sdk/client-ecs");
const {
  ElasticLoadBalancingV2Client,
  CreateRuleCommand,
  CreateTargetGroupCommand,
  DescribeRulesCommand,
  DescribeTargetGroupsCommand,
  ModifyTargetGroupAttributesCommand,
} = require("@aws-sdk/client-elastic-load-balancing-v2");

const ecs = new ECSClient({});
const elbv2 = new ElasticLoadBalancingV2Client({});

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function optionalEnv(name, fallback = "") {
  return process.env[name] || fallback;
}

function csvEnv(name) {
  return requireEnv(name)
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function numberEnv(name) {
  const parsed = Number(requireEnv(name));
  if (!Number.isFinite(parsed)) {
    throw new Error(`Environment variable ${name} must be a number`);
  }
  return parsed;
}

function repositoryNameFromEvent(event) {
  const repositoryName =
    event?.detail?.["repository-name"] || event?.detail?.repositoryName;

  if (!repositoryName) {
    throw new Error("Event did not contain detail.repository-name");
  }

  return repositoryName;
}

function imageTagFromEvent(event) {
  const imageTag = event?.detail?.["image-tag"] || event?.detail?.imageTag;
  if (!imageTag) {
    throw new Error("Event did not contain detail.image-tag");
  }
  return imageTag;
}

function hash(value, length = 8) {
  return crypto.createHash("sha256").update(value).digest("hex").slice(0, length);
}

function slugify(value, maxLength) {
  const base = value
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  const suffix = hash(value);
  const prefixLength = Math.max(1, maxLength - suffix.length - 1);
  return `${base.slice(0, prefixLength).replace(/-$/g, "")}-${suffix}`;
}

function tags(projectName, repositoryName) {
  return [
    { key: "Project", value: projectName },
    { key: "ManagedBy", value: "ecr-to-ecs-deploy-lambda" },
    { key: "EcrRepository", value: repositoryName },
  ];
}

function appEnvironment() {
  const raw = optionalEnv("APP_ENVIRONMENT_JSON", "{}");
  const parsed = JSON.parse(raw);

  return Object.entries(parsed).map(([name, value]) => ({
    name,
    value: String(value),
  }));
}

async function serviceExists(cluster, serviceName) {
  const response = await ecs.send(
    new DescribeServicesCommand({
      cluster,
      services: [serviceName],
    })
  );

  const service = response.services?.[0];
  return Boolean(service && service.status !== "INACTIVE");
}

async function ensureTargetGroup({ name, vpcId, containerPort, healthCheckPath, tagList }) {
  try {
    const existing = await elbv2.send(
      new DescribeTargetGroupsCommand({
        Names: [name],
      })
    );

    const targetGroupArn = existing.TargetGroups?.[0]?.TargetGroupArn;
    if (targetGroupArn) {
      return targetGroupArn;
    }
  } catch (error) {
    if (
      error.name !== "TargetGroupNotFound" &&
      error.name !== "TargetGroupNotFoundException"
    ) {
      throw error;
    }
  }

  const created = await elbv2.send(
    new CreateTargetGroupCommand({
      Name: name,
      Protocol: "HTTP",
      Port: containerPort,
      VpcId: vpcId,
      TargetType: "ip",
      HealthCheckEnabled: true,
      HealthCheckProtocol: "HTTP",
      HealthCheckPath: healthCheckPath,
      HealthCheckPort: "traffic-port",
      Matcher: {
        HttpCode: "200-399",
      },
      Tags: tagList.map(({ key, value }) => ({ Key: key, Value: value })),
    })
  );

  const targetGroupArn = created.TargetGroups?.[0]?.TargetGroupArn;
  if (!targetGroupArn) {
    throw new Error(`Failed to create target group ${name}`);
  }

  await elbv2.send(
    new ModifyTargetGroupAttributesCommand({
      TargetGroupArn: targetGroupArn,
      Attributes: [
        {
          Key: "deregistration_delay.timeout_seconds",
          Value: "30",
        },
      ],
    })
  );

  return targetGroupArn;
}

function ruleMatches(rule, route) {
  const conditions = rule.Conditions || [];
  if (route.type === "host") {
    return conditions.some(
      (condition) =>
        condition.Field === "host-header" &&
        condition.Values?.includes(route.host)
    );
  }

  return conditions.some(
    (condition) =>
      condition.Field === "path-pattern" &&
      condition.Values?.some((value) => route.paths.includes(value))
  );
}

async function nextRulePriority(listenerArn, seed) {
  const rules = await elbv2.send(
    new DescribeRulesCommand({
      ListenerArn: listenerArn,
    })
  );

  const used = new Set(
    (rules.Rules || [])
      .map((rule) => Number(rule.Priority))
      .filter((priority) => Number.isInteger(priority))
  );

  let priority = 100 + (parseInt(hash(seed, 6), 16) % 49000);
  while (used.has(priority)) {
    priority += 1;
    if (priority > 50000) {
      priority = 100;
    }
  }

  return priority;
}

async function ensureListenerRule({ listenerArn, targetGroupArn, route, repositoryName }) {
  const rules = await elbv2.send(
    new DescribeRulesCommand({
      ListenerArn: listenerArn,
    })
  );

  const existing = (rules.Rules || []).find((rule) => ruleMatches(rule, route));
  if (existing?.RuleArn) {
    return existing.RuleArn;
  }

  const priority = await nextRulePriority(listenerArn, repositoryName);
  const conditions =
    route.type === "host"
      ? [
          {
            Field: "host-header",
            HostHeaderConfig: {
              Values: [route.host],
            },
          },
        ]
      : [
          {
            Field: "path-pattern",
            PathPatternConfig: {
              Values: route.paths,
            },
          },
        ];

  const created = await elbv2.send(
    new CreateRuleCommand({
      ListenerArn: listenerArn,
      Priority: priority,
      Conditions: conditions,
      Actions: [
        {
          Type: "forward",
          TargetGroupArn: targetGroupArn,
        },
      ],
    })
  );

  const ruleArn = created.Rules?.[0]?.RuleArn;
  if (!ruleArn) {
    throw new Error(`Failed to create listener rule for ${repositoryName}`);
  }

  return ruleArn;
}

async function registerTaskDefinition({
  family,
  imageUri,
  containerName,
  containerPort,
  cpu,
  memory,
  executionRoleArn,
  taskRoleArn,
  logGroup,
  region,
  tagList,
}) {
  const response = await ecs.send(
    new RegisterTaskDefinitionCommand({
      family,
      networkMode: "awsvpc",
      requiresCompatibilities: ["FARGATE"],
      cpu: String(cpu),
      memory: String(memory),
      executionRoleArn,
      taskRoleArn,
      containerDefinitions: [
        {
          name: containerName,
          image: imageUri,
          essential: true,
          portMappings: [
            {
              containerPort,
              hostPort: containerPort,
              protocol: "tcp",
            },
          ],
          environment: appEnvironment(),
          logConfiguration: {
            logDriver: "awslogs",
            options: {
              "awslogs-group": logGroup,
              "awslogs-region": region,
              "awslogs-stream-prefix": containerName,
            },
          },
        },
      ],
      tags: tagList,
    })
  );

  const taskDefinitionArn = response.taskDefinition?.taskDefinitionArn;
  if (!taskDefinitionArn) {
    throw new Error(`Failed to register task definition ${family}`);
  }

  return taskDefinitionArn;
}

function routeFor(repositoryName, serviceSlug) {
  const publicDomainName = optionalEnv("PUBLIC_DOMAIN_NAME");
  const albDnsName = requireEnv("ALB_DNS_NAME");

  if (publicDomainName) {
    const host = `${serviceSlug}.${publicDomainName}`;
    return {
      type: "host",
      host,
      url: `http://${host}`,
    };
  }

  const paths = [`/${serviceSlug}`, `/${serviceSlug}/*`];
  return {
    type: "path",
    paths,
    url: `http://${albDnsName}/${serviceSlug}`,
  };
}

function postJson(url, payload, secret) {
  if (!url) {
    return Promise.resolve();
  }

  const body = JSON.stringify(payload);
  const parsed = new URL(url);
  const client = parsed.protocol === "https:" ? https : http;

  const headers = {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
  };

  if (secret) {
    headers["x-deploy-callback-secret"] = secret;
  }

  return new Promise((resolve, reject) => {
    const request = client.request(
      {
        method: "POST",
        hostname: parsed.hostname,
        port: parsed.port || undefined,
        path: `${parsed.pathname}${parsed.search}`,
        headers,
      },
      (response) => {
        let responseBody = "";
        response.on("data", (chunk) => {
          responseBody += chunk;
        });
        response.on("end", () => {
          if (response.statusCode >= 200 && response.statusCode < 300) {
            resolve();
            return;
          }

          reject(
            new Error(
              `Callback failed with ${response.statusCode}: ${responseBody.slice(0, 500)}`
            )
          );
        });
      }
    );

    request.on("error", reject);
    request.write(body);
    request.end();
  });
}

async function notifyBackend(payload) {
  const callbackUrl = optionalEnv("BACKEND_CALLBACK_URL");
  if (!callbackUrl) {
    console.log("BACKEND_CALLBACK_URL is not set; skipping backend callback");
    return;
  }

  try {
    await postJson(callbackUrl, payload, optionalEnv("BACKEND_CALLBACK_SECRET"));
    console.log("Backend deployment callback sent");
  } catch (error) {
    console.error("Backend deployment callback failed", error);
  }
}

exports.handler = async (event) => {
  console.log("Received ECR event", JSON.stringify(event));

  const repositoryName = repositoryNameFromEvent(event);
  const imageTag = imageTagFromEvent(event);
  const accountId = requireEnv("AWS_ACCOUNT_ID");
  const region = requireEnv("AWS_REGION");
  const imageUri = `${accountId}.dkr.ecr.${region}.amazonaws.com/${repositoryName}:${imageTag}`;

  try {
    const projectName = requireEnv("PROJECT_NAME");
    const repositoryPrefix = optionalEnv("ECR_REPOSITORY_PREFIX");

    if (repositoryPrefix && !repositoryName.startsWith(repositoryPrefix)) {
      console.log(`Ignoring ${repositoryName}; expected prefix ${repositoryPrefix}`);
      return { ignored: true, repositoryName, imageTag };
    }

    const serviceSlug = slugify(`${projectName}-${repositoryName}`, 48);
    const serviceName = serviceSlug;
    const targetGroupName = slugify(`${projectName}-${repositoryName}`, 32);
    const taskFamily = serviceSlug;
    const containerName = requireEnv("CONTAINER_NAME");
    const containerPort = numberEnv("CONTAINER_PORT");
    const cluster = requireEnv("ECS_CLUSTER_NAME");
    const tagList = tags(projectName, repositoryName);
    const route = routeFor(repositoryName, serviceSlug);

    const taskDefinitionArn = await registerTaskDefinition({
      family: taskFamily,
      imageUri,
      containerName,
      containerPort,
      cpu: numberEnv("TASK_CPU"),
      memory: numberEnv("TASK_MEMORY"),
      executionRoleArn: requireEnv("ECS_TASK_EXECUTION_ROLE"),
      taskRoleArn: requireEnv("ECS_TASK_ROLE"),
      logGroup: requireEnv("ECS_LOG_GROUP"),
      region,
      tagList,
    });

    const targetGroupArn = await ensureTargetGroup({
      name: targetGroupName,
      vpcId: requireEnv("VPC_ID"),
      containerPort,
      healthCheckPath: requireEnv("HEALTH_CHECK_PATH"),
      tagList,
    });

    const ruleArn = await ensureListenerRule({
      listenerArn: requireEnv("ALB_LISTENER_ARN"),
      targetGroupArn,
      route,
      repositoryName,
    });

    const exists = await serviceExists(cluster, serviceName);

    if (exists) {
      await ecs.send(
        new UpdateServiceCommand({
          cluster,
          service: serviceName,
          taskDefinition: taskDefinitionArn,
          forceNewDeployment: true,
        })
      );
    } else {
      await ecs.send(
        new CreateServiceCommand({
          cluster,
          serviceName,
          taskDefinition: taskDefinitionArn,
          desiredCount: numberEnv("DESIRED_COUNT"),
          launchType: "FARGATE",
          healthCheckGracePeriodSeconds: 60,
          deploymentConfiguration: {
            minimumHealthyPercent: 50,
            maximumPercent: 200,
          },
          networkConfiguration: {
            awsvpcConfiguration: {
              subnets: csvEnv("ECS_SUBNET_IDS"),
              securityGroups: csvEnv("ECS_SECURITY_GROUP_IDS"),
              assignPublicIp: requireEnv("ASSIGN_PUBLIC_IP"),
            },
          },
          loadBalancers: [
            {
              targetGroupArn,
              containerName,
              containerPort,
            },
          ],
          tags: tagList,
        })
      );
    }

    console.log(
      `${exists ? "Updated" : "Created"} ECS service ${serviceName} using ${imageUri}`
    );

    const result = {
      repositoryName,
      imageTag,
      imageUri,
      serviceName,
      taskDefinitionArn,
      targetGroupArn,
      ruleArn,
      url: route.url,
    };

    await notifyBackend({
      image_uri: imageUri,
      status: "deployed",
      public_url: route.url,
      ecs_service_name: serviceName,
      task_definition_arn: taskDefinitionArn,
      target_group_arn: targetGroupArn,
      error_message: null,
    });

    return result;
  } catch (error) {
    await notifyBackend({
      image_uri: imageUri,
      status: "error",
      error_message: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
};
