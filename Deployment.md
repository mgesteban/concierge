# BoardBreeze Concierge — AWS ECS (Fargate) Deployment Plan

**Goal:** move the Concierge from Grace's laptop (uvicorn + ngrok) to AWS ECS Fargate so it runs 24/7 for real BoardBreeze subscribers, with a stable HTTPS endpoint, predictable monthly cost, and the same operational pattern as the existing `appboardbreeze.com` service (which already runs on ECS Fargate in us-east-2).

**Why ECS over App Runner:** the rest of BoardBreeze already runs on ECS Fargate in us-east-2 — same VPC, same cluster, same operational muscle memory. Reusing that cluster means we share VPC/subnets/NAT, reuse Grace's existing IAM patterns, and ops stays in one console. App Runner would have been faster the first time but creates a second mental model to maintain.

**Why a separate ALB (not the existing one):** the existing ALB is owned by the `BoardBreezeStack` CDK stack. Any listener-rule change we make in the console gets wiped on the next CDK deploy. A small dedicated ALB for the concierge isolates risk from the prod stack and is easy to tear down.

**Estimated total time:** 90–120 minutes the first time, mostly waiting on ACM cert validation + first ECR push.
**Estimated monthly cost:** ~$50 (Fargate 1 vCPU / 2 GB always-on ~$25 + ALB ~$22 + Secrets Manager ~$0.40 + CloudWatch ~$2). Plus your existing Supabase / Voyage / Anthropic / Twilio / ElevenLabs costs (unchanged).
**Rollback path:** if anything goes wrong post-deploy, point Twilio webhooks back at `https://boardbreeze.ngrok.app` (your laptop) — your local stack still works exactly as before. Two clicks in Twilio Console, ~30 seconds. ECS service stays up but takes no traffic.

---

## Account & infra facts (already verified)

These are filled in from your live AWS account — every command in this doc uses them. If anything below changes, search/replace once at the top.

| Thing | Value |
|---|---|
| AWS account ID | `842676016582` |
| Region | `us-east-2` (Ohio) |
| ECS cluster (reuse) | `BoardBreezeStack-BoardBreezeClusterFD9D5A42-lg43oJpmrEpk` |
| VPC (reuse) | `vpc-05ac77ee884e81d26` |
| Public subnet A (reuse) | `subnet-086f90260cc8b418a` (us-east-2a) |
| Public subnet B (reuse) | `subnet-0c3d92b6ca0b49c37` (us-east-2b) |
| New ECR repo | `boardbreeze-concierge` |
| New ALB | `boardbreeze-concierge-alb` |
| New target group | `boardbreeze-concierge-tg` |
| New service | `boardbreeze-concierge` |
| Task definition family | `boardbreeze-concierge` |
| Secret name | `boardbreeze-concierge/env` |
| Log group | `/ecs/boardbreeze-concierge` |
| Public domain | `concierge.appboardbreeze.com` |
| DNS host | Vercel (registrar = Vercel; DNS panel = Vercel) |

Set these as shell vars before running any AWS CLI commands:

```bash
export AWS_REGION=us-east-2
export AWS_ACCOUNT_ID=842676016582
export CLUSTER=BoardBreezeStack-BoardBreezeClusterFD9D5A42-lg43oJpmrEpk
export VPC_ID=vpc-05ac77ee884e81d26
export SUBNET_A=subnet-086f90260cc8b418a
export SUBNET_B=subnet-0c3d92b6ca0b49c37
export ECR_REPO=boardbreeze-concierge
export SERVICE=boardbreeze-concierge
export TASK_FAMILY=boardbreeze-concierge
export ALB_NAME=boardbreeze-concierge-alb
export TG_NAME=boardbreeze-concierge-tg
export LOG_GROUP=/ecs/boardbreeze-concierge
export DOMAIN=concierge.appboardbreeze.com
export SECRET_NAME=boardbreeze-concierge/env
```

---

## Pre-flight checklist (5 min)

Each item should be a "yes" — if any is "no," stop and fix that first.

- [ ] **AWS CLI works.** `aws sts get-caller-identity` returns account `842676016582`.
- [ ] **Docker daemon running.** `docker ps` returns without error. (We need to build the image locally.)
- [ ] **Repo on `main` and clean.** `git status` should be clean (or only the new deploy files staged).
- [ ] **Local `.env` is complete and working.** Recent test calls confirm Anthropic, Supabase, Voyage, Twilio, ElevenLabs all work. We'll copy values into Secrets Manager.
- [ ] **Vercel DNS access.** You can sign in to Vercel and edit DNS records on `appboardbreeze.com`. (You'll add 2 CNAMEs there: one for ACM cert validation, one for the final hostname.)
- [ ] **Twilio Console access.** Edit the webhook URLs on your concierge phone number.
- [ ] **CMA agent already updated.** Phase 0.5 from the previous plan was done before this doc was switched to ECS. (If unsure, run `.venv/bin/python -m scripts.update_cma_agent` and confirm `search_product_kb` is in the tools list.)

---

## Architecture overview

```
                                         ┌──────────────────────────┐
   Twilio caller / SMS  ───HTTPS───▶     │ concierge.appboardbreeze │  (Vercel CNAME)
                                         │           .com           │
                                         └────────────┬─────────────┘
                                                      │
                                                      ▼
                                  ┌─────────────────────────────────────┐
                                  │     boardbreeze-concierge-alb       │  (new, dedicated)
                                  │      :443 → ACM cert (DNS-validated)│
                                  │      :80  → :443 redirect           │
                                  └────────────────┬────────────────────┘
                                                   │
                                                   ▼
                                  ┌─────────────────────────────────────┐
                                  │   boardbreeze-concierge-tg          │
                                  │   target type: ip, port 8000, /health
                                  └────────────────┬────────────────────┘
                                                   │
                                                   ▼
              ┌──────────────────────────────────────────────────────────────┐
              │ ECS cluster: BoardBreezeStack-BoardBreezeCluster... (reused) │
              │   • existing service: BoardBreezeWebSocketService (untouched)│
              │   • NEW service: boardbreeze-concierge                       │
              │       └─ Fargate task: 1 vCPU, 2 GB                          │
              │            └─ container "app": 842676016582.dkr.ecr.../boardbreeze-concierge:<sha>
              │                 ├─ port 8000                                 │
              │                 └─ secrets ← Secrets Manager (boardbreeze-concierge/env)
              └──────────────────────────────────────────────────────────────┘
                                                   │
                                                   ▼
                                CloudWatch Logs → /ecs/boardbreeze-concierge
```

Two security groups:
- **`alb-sg`** — ALB ingress from `0.0.0.0/0` on 80 + 443.
- **`task-sg`** — task ingress on 8000 only from `alb-sg`. Egress to anywhere (Anthropic, Twilio, Supabase, etc.).

---

## Phase 1 — Add containerization files (5 min)

### 1.1 `Dockerfile`

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Decisions baked in:**
- `python:3.11-slim` — matches `requirements.txt` minimum; ~150 MB base.
- `curl` is installed only because the Docker `HEALTHCHECK` needs it; ALB health check is independent.
- `--host 0.0.0.0` so the container's port 8000 is reachable from outside the container namespace.
- No build-time secrets. All secrets enter at runtime via Secrets Manager.

### 1.2 `.dockerignore`

```
.git
.gitignore
__pycache__
*.py[cod]
.venv
venv
env
*.egg-info
.pytest_cache

.env
.env.*
!.env.example

.vscode
.idea
*.swp
*.code-workspace

*.pdf
boardbreeze-concierge-playbook-*.md
BoardBreeze Comprehensive FAQ*.md
Questions*.md
video_script*.md
Video Demo/
governance_tools_extracted/
governance_tools.zip

CHANGELOG.md
Deployment.md
Progress.md
README.md
notes/

apprunner.yaml
tests
```

### 1.3 Sanity-check the build locally

```bash
cd /home/grace/boardbreeze-concierge-voice
docker build -t boardbreeze-concierge:dev .
# Expect: "naming to docker.io/library/boardbreeze-concierge:dev done"
docker images boardbreeze-concierge
# Expect ~600–800 MB final image size.
```

If it builds, we're ready to push to ECR.

### 1.4 Delete `apprunner.yaml`

```bash
git rm apprunner.yaml
```

(Done so future readers don't get confused about which platform we're targeting.)

---

## Phase 2 — ECR repo + image push (15 min)

### 2.1 Create the ECR repository

```bash
aws ecr create-repository \
  --repository-name "$ECR_REPO" \
  --region "$AWS_REGION" \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256
```

Output should include `"repositoryUri": "842676016582.dkr.ecr.us-east-2.amazonaws.com/boardbreeze-concierge"`.

### 2.2 Authenticate Docker to ECR

```bash
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
# Expect: "Login Succeeded"
```

### 2.3 Tag + push

```bash
GIT_SHA=$(git rev-parse --short HEAD)
ECR_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO"

docker build -t "$ECR_URI:$GIT_SHA" -t "$ECR_URI:latest" .
docker push "$ECR_URI:$GIT_SHA"
docker push "$ECR_URI:latest"

echo "Pushed: $ECR_URI:$GIT_SHA"
```

First push is slow (~5 min, uploading every layer). Subsequent pushes only upload changed layers.

### 2.4 Verify in console

```bash
aws ecr describe-images --repository-name "$ECR_REPO" --region "$AWS_REGION" \
  --query 'imageDetails[].[imageTags,imagePushedAt]' --output table
```

You should see two tags: `latest` and `<git-sha>`.

---

## Phase 3 — Secrets Manager (10 min)

We store all 11 env values as **a single JSON secret**. ECS supports either single-key secrets or JSON-key references; one JSON secret is cheaper ($0.40/mo vs $0.40 × 11) and easier to rotate.

### 3.1 Build the JSON locally from `.env`

```bash
cd /home/grace/boardbreeze-concierge-voice

# Generate the JSON file in /tmp (NOT in the repo).
python3 - <<'PY' > /tmp/concierge-secrets.json
import os
from dotenv import load_dotenv
import json
load_dotenv(".env")
keys = [
    "ANTHROPIC_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "VOYAGE_API_KEY",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "GRACE_PHONE_NUMBER",
    "GRACE_EMAIL",
]
out = {k: os.environ[k] for k in keys}
print(json.dumps(out, indent=2))
PY

# Sanity-check it has all 11 keys, no nulls:
python3 -c 'import json; d=json.load(open("/tmp/concierge-secrets.json")); print(len(d), "keys"); assert all(d.values())'
# Expect: "11 keys"
```

### 3.2 Push the secret

```bash
aws secretsmanager create-secret \
  --name "$SECRET_NAME" \
  --description "BoardBreeze Concierge env vars (Anthropic, Twilio, Supabase, Voyage, ElevenLabs, Grace contact)" \
  --secret-string file:///tmp/concierge-secrets.json \
  --region "$AWS_REGION"

# Capture the ARN — needed in the task definition.
export SECRET_ARN=$(aws secretsmanager describe-secret \
  --secret-id "$SECRET_NAME" --region "$AWS_REGION" \
  --query 'ARN' --output text)
echo "$SECRET_ARN"
```

Then **shred the temp file**:

```bash
shred -u /tmp/concierge-secrets.json
```

### 3.3 Future rotations

To change one value: `aws secretsmanager update-secret --secret-id "$SECRET_NAME" --secret-string '<new-json>'`. Then **force a new ECS deployment** (`aws ecs update-service ... --force-new-deployment`) so tasks pick up the new value.

---

## Phase 4 — IAM roles (10 min)

Two roles:

- **Execution role** (`BoardbreezeConciergeExecutionRole`) — used by the ECS agent to pull the image from ECR, fetch the secret from Secrets Manager, and write logs to CloudWatch. *Boilerplate; never holds business credentials.*
- **Task role** (`BoardbreezeConciergeTaskRole`) — assumed by the running container itself. The concierge today only talks to Anthropic / Twilio / Supabase / etc. via API keys (already in env), so it doesn't need any AWS-side permissions. We create the role anyway with no policies attached, so we have a slot for future AWS calls (e.g. S3, SES) without redeploying the task definition.

### 4.1 Create the execution role

```bash
cat > /tmp/ecs-trust.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
JSON

aws iam create-role \
  --role-name BoardbreezeConciergeExecutionRole \
  --assume-role-policy-document file:///tmp/ecs-trust.json

aws iam attach-role-policy \
  --role-name BoardbreezeConciergeExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

Add Secrets Manager read permission scoped to this one secret:

```bash
cat > /tmp/secret-read.json <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["secretsmanager:GetSecretValue"],
    "Resource": "$SECRET_ARN"
  }]
}
JSON

aws iam put-role-policy \
  --role-name BoardbreezeConciergeExecutionRole \
  --policy-name ReadConciergeSecret \
  --policy-document file:///tmp/secret-read.json
```

### 4.2 Create the task role (empty policy, future-proof slot)

```bash
aws iam create-role \
  --role-name BoardbreezeConciergeTaskRole \
  --assume-role-policy-document file:///tmp/ecs-trust.json
```

Capture both role ARNs:

```bash
export EXEC_ROLE_ARN=$(aws iam get-role --role-name BoardbreezeConciergeExecutionRole --query 'Role.Arn' --output text)
export TASK_ROLE_ARN=$(aws iam get-role --role-name BoardbreezeConciergeTaskRole --query 'Role.Arn' --output text)
echo "EXEC=$EXEC_ROLE_ARN"
echo "TASK=$TASK_ROLE_ARN"
```

---

## Phase 5 — CloudWatch log group + task definition (10 min)

### 5.1 Create the log group

```bash
aws logs create-log-group --log-group-name "$LOG_GROUP" --region "$AWS_REGION"
aws logs put-retention-policy --log-group-name "$LOG_GROUP" --retention-in-days 30 --region "$AWS_REGION"
```

(30-day retention — small bill, plenty for incident triage.)

### 5.2 Build the task definition JSON

```bash
GIT_SHA=$(git rev-parse --short HEAD)
ECR_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO"

cat > /tmp/taskdef.json <<JSON
{
  "family": "$TASK_FAMILY",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "$EXEC_ROLE_ARN",
  "taskRoleArn": "$TASK_ROLE_ARN",
  "runtimePlatform": {
    "cpuArchitecture": "X86_64",
    "operatingSystemFamily": "LINUX"
  },
  "containerDefinitions": [{
    "name": "app",
    "image": "$ECR_URI:$GIT_SHA",
    "essential": true,
    "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
    "environment": [
      {"name": "HOST", "value": "0.0.0.0"},
      {"name": "PORT", "value": "8000"},
      {"name": "PUBLIC_BASE_URL", "value": "https://$DOMAIN"}
    ],
    "secrets": [
      {"name": "ANTHROPIC_API_KEY",    "valueFrom": "$SECRET_ARN:ANTHROPIC_API_KEY::"},
      {"name": "SUPABASE_URL",         "valueFrom": "$SECRET_ARN:SUPABASE_URL::"},
      {"name": "SUPABASE_SERVICE_KEY", "valueFrom": "$SECRET_ARN:SUPABASE_SERVICE_KEY::"},
      {"name": "VOYAGE_API_KEY",       "valueFrom": "$SECRET_ARN:VOYAGE_API_KEY::"},
      {"name": "TWILIO_ACCOUNT_SID",   "valueFrom": "$SECRET_ARN:TWILIO_ACCOUNT_SID::"},
      {"name": "TWILIO_AUTH_TOKEN",    "valueFrom": "$SECRET_ARN:TWILIO_AUTH_TOKEN::"},
      {"name": "TWILIO_PHONE_NUMBER",  "valueFrom": "$SECRET_ARN:TWILIO_PHONE_NUMBER::"},
      {"name": "ELEVENLABS_API_KEY",   "valueFrom": "$SECRET_ARN:ELEVENLABS_API_KEY::"},
      {"name": "ELEVENLABS_VOICE_ID",  "valueFrom": "$SECRET_ARN:ELEVENLABS_VOICE_ID::"},
      {"name": "GRACE_PHONE_NUMBER",   "valueFrom": "$SECRET_ARN:GRACE_PHONE_NUMBER::"},
      {"name": "GRACE_EMAIL",          "valueFrom": "$SECRET_ARN:GRACE_EMAIL::"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "$LOG_GROUP",
        "awslogs-region": "$AWS_REGION",
        "awslogs-stream-prefix": "ecs"
      }
    },
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -fsS http://127.0.0.1:8000/health || exit 1"],
      "interval": 30,
      "timeout": 5,
      "retries": 3,
      "startPeriod": 20
    }
  }]
}
JSON
```

The `valueFrom` syntax `arn:secret:KEY::` references one JSON key inside the secret — that's how a single Secrets Manager entry feeds 11 separate env vars into the container.

### 5.3 Register the task definition

```bash
aws ecs register-task-definition \
  --cli-input-json file:///tmp/taskdef.json \
  --region "$AWS_REGION"

# Capture the ARN of the latest revision:
export TASK_DEF_ARN=$(aws ecs describe-task-definition \
  --task-definition "$TASK_FAMILY" --region "$AWS_REGION" \
  --query 'taskDefinition.taskDefinitionArn' --output text)
echo "$TASK_DEF_ARN"
```

---

## Phase 6 — ALB, ACM cert, target group (20 min)

### 6.1 Security groups

```bash
# ALB SG — public ingress on 80/443
aws ec2 create-security-group \
  --group-name boardbreeze-concierge-alb-sg \
  --description "ALB ingress for concierge" \
  --vpc-id "$VPC_ID" --region "$AWS_REGION"

export ALB_SG=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=boardbreeze-concierge-alb-sg" "Name=vpc-id,Values=$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text --region "$AWS_REGION")

aws ec2 authorize-security-group-ingress --group-id "$ALB_SG" \
  --protocol tcp --port 80 --cidr 0.0.0.0/0 --region "$AWS_REGION"
aws ec2 authorize-security-group-ingress --group-id "$ALB_SG" \
  --protocol tcp --port 443 --cidr 0.0.0.0/0 --region "$AWS_REGION"

# Task SG — port 8000 from ALB SG only
aws ec2 create-security-group \
  --group-name boardbreeze-concierge-task-sg \
  --description "Fargate task ingress for concierge" \
  --vpc-id "$VPC_ID" --region "$AWS_REGION"

export TASK_SG=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=boardbreeze-concierge-task-sg" "Name=vpc-id,Values=$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text --region "$AWS_REGION")

aws ec2 authorize-security-group-ingress --group-id "$TASK_SG" \
  --protocol tcp --port 8000 --source-group "$ALB_SG" --region "$AWS_REGION"

echo "ALB_SG=$ALB_SG"
echo "TASK_SG=$TASK_SG"
```

### 6.2 Create the target group

```bash
aws elbv2 create-target-group \
  --name "$TG_NAME" \
  --protocol HTTP --port 8000 \
  --target-type ip \
  --vpc-id "$VPC_ID" \
  --health-check-protocol HTTP \
  --health-check-path /health \
  --health-check-interval-seconds 15 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --matcher HttpCode=200 \
  --region "$AWS_REGION"

export TG_ARN=$(aws elbv2 describe-target-groups --names "$TG_NAME" \
  --query 'TargetGroups[0].TargetGroupArn' --output text --region "$AWS_REGION")
echo "$TG_ARN"
```

`target-type ip` is required for Fargate (vs. `instance` for EC2).

### 6.3 Create the ALB

```bash
aws elbv2 create-load-balancer \
  --name "$ALB_NAME" \
  --type application \
  --scheme internet-facing \
  --ip-address-type ipv4 \
  --subnets "$SUBNET_A" "$SUBNET_B" \
  --security-groups "$ALB_SG" \
  --region "$AWS_REGION"

export ALB_ARN=$(aws elbv2 describe-load-balancers --names "$ALB_NAME" \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text --region "$AWS_REGION")
export ALB_DNS=$(aws elbv2 describe-load-balancers --names "$ALB_NAME" \
  --query 'LoadBalancers[0].DNSName' --output text --region "$AWS_REGION")
echo "ALB_ARN=$ALB_ARN"
echo "ALB_DNS=$ALB_DNS"
```

### 6.4 Request the ACM certificate

```bash
aws acm request-certificate \
  --domain-name "$DOMAIN" \
  --validation-method DNS \
  --region "$AWS_REGION"

export CERT_ARN=$(aws acm list-certificates --region "$AWS_REGION" \
  --query "CertificateSummaryList[?DomainName=='$DOMAIN'].CertificateArn | [0]" \
  --output text)
echo "$CERT_ARN"
```

ACM cert + ALB **must be in the same region** (us-east-2). DNS validation requires you to add a CNAME in Vercel.

### 6.5 Add the cert-validation CNAME to Vercel

```bash
aws acm describe-certificate --certificate-arn "$CERT_ARN" --region "$AWS_REGION" \
  --query 'Certificate.DomainValidationOptions[0].ResourceRecord' --output table
```

That prints something like:

```
| Name  | _abcd1234.concierge.appboardbreeze.com.       |
| Type  | CNAME                                         |
| Value | _xyz5678.acm-validations.aws.                 |
```

**In Vercel:**
1. Sign in → **appboardbreeze.com** project (or the dashboard for the domain).
2. **Settings → Domains** (or **Domains** in the top nav).
3. Click **appboardbreeze.com** → **DNS Records** tab.
4. **Add Record**:
   - Type: `CNAME`
   - Name: `_abcd1234.concierge` *(use the part of the AWS Name field that comes BEFORE `.appboardbreeze.com.` — Vercel auto-appends the domain)*
   - Value: `_xyz5678.acm-validations.aws.` (paste exactly, including the trailing dot if Vercel allows; usually it strips it)
   - TTL: default (60 sec or whatever Vercel offers)
5. Save.

Wait for validation:

```bash
# Poll every 30s. Status flips Pending → Issued in 1–10 min once Vercel propagates.
aws acm describe-certificate --certificate-arn "$CERT_ARN" --region "$AWS_REGION" \
  --query 'Certificate.Status' --output text
```

When it returns `ISSUED`, continue.

### 6.6 ALB listeners — :443 with cert + :80 redirect

```bash
# HTTPS listener — forwards to target group
aws elbv2 create-listener \
  --load-balancer-arn "$ALB_ARN" \
  --protocol HTTPS --port 443 \
  --certificates "CertificateArn=$CERT_ARN" \
  --ssl-policy ELBSecurityPolicy-TLS13-1-2-2021-06 \
  --default-actions "Type=forward,TargetGroupArn=$TG_ARN" \
  --region "$AWS_REGION"

# HTTP :80 → :443 redirect
aws elbv2 create-listener \
  --load-balancer-arn "$ALB_ARN" \
  --protocol HTTP --port 80 \
  --default-actions '[{"Type":"redirect","RedirectConfig":{"Protocol":"HTTPS","Port":"443","StatusCode":"HTTP_301"}}]' \
  --region "$AWS_REGION"
```

---

## Phase 7 — Create the ECS service (10 min)

### 7.1 Service definition

```bash
cat > /tmp/service.json <<JSON
{
  "cluster": "$CLUSTER",
  "serviceName": "$SERVICE",
  "taskDefinition": "$TASK_FAMILY",
  "desiredCount": 1,
  "launchType": "FARGATE",
  "platformVersion": "LATEST",
  "networkConfiguration": {
    "awsvpcConfiguration": {
      "subnets": ["$SUBNET_A", "$SUBNET_B"],
      "securityGroups": ["$TASK_SG"],
      "assignPublicIp": "ENABLED"
    }
  },
  "loadBalancers": [{
    "targetGroupArn": "$TG_ARN",
    "containerName": "app",
    "containerPort": 8000
  }],
  "healthCheckGracePeriodSeconds": 60,
  "deploymentConfiguration": {
    "maximumPercent": 200,
    "minimumHealthyPercent": 100,
    "deploymentCircuitBreaker": {"enable": true, "rollback": true}
  },
  "enableExecuteCommand": true,
  "propagateTags": "SERVICE",
  "tags": [
    {"key": "project", "value": "boardbreeze"},
    {"key": "component", "value": "concierge"}
  ]
}
JSON
```

**Why `assignPublicIp: ENABLED`:** the existing cluster's CDK stack appears to use public subnets without a NAT gateway. Public IP on the task lets it pull from ECR + reach Anthropic/Twilio without paying for NAT. (If your VPC actually has NAT and private subnets you want to use, change to `DISABLED` and use the private subnet IDs.)

**Why `enableExecuteCommand: true`:** lets you `aws ecs execute-command` into the running container for live debugging — same as `kubectl exec`.

### 7.2 Create the service

```bash
aws ecs create-service \
  --cli-input-json file:///tmp/service.json \
  --region "$AWS_REGION"
```

### 7.3 Watch it come up

```bash
# Tail events:
aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" --region "$AWS_REGION" \
  --query 'services[0].events[0:10]' --output table

# Watch the task transition Pending → Running:
aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" --region "$AWS_REGION"

# Once running, check target health (this is the gate to traffic):
aws elbv2 describe-target-health --target-group-arn "$TG_ARN" --region "$AWS_REGION" \
  --query 'TargetHealthDescriptions[].[Target.Id,TargetHealth.State,TargetHealth.Reason]' --output table
```

You're looking for `State=healthy`. First-time go-healthy takes 1–3 min after the task hits `RUNNING`.

### 7.4 Tail container logs

```bash
aws logs tail "$LOG_GROUP" --follow --region "$AWS_REGION"
```

Look for the uvicorn startup banner. If you see a Python traceback instead, the most common causes are:
- Missing/invalid secret key (e.g. typo'd JSON key in Secrets Manager)
- pip install failing because requirements changed but image is stale (rebuild + push)
- App crashes because `PUBLIC_BASE_URL` validation fails — confirm it's set to `https://concierge.appboardbreeze.com`

---

## Phase 8 — DNS cutover + Twilio webhook flip (10 min)

### 8.1 Add the final CNAME in Vercel

In the same Vercel DNS panel from 6.5:

- Type: `CNAME`
- Name: `concierge`
- Value: `<ALB_DNS>` (what `echo "$ALB_DNS"` printed in 6.3, e.g. `boardbreeze-concierge-alb-1234567890.us-east-2.elb.amazonaws.com`)
- TTL: 60

Save. Wait ~1 min for propagation.

### 8.2 Verify HTTPS

```bash
curl -sS "https://$DOMAIN/health"
# Expect: {"status":"ok"}

curl -sS "https://$DOMAIN/"
# Expect the BoardBreeze Concierge service banner JSON
```

If TLS handshake fails: cert may still be propagating (give it 5 min) or the `ALB_DNS` CNAME hasn't propagated yet (`dig concierge.appboardbreeze.com`).

### 8.3 Flip Twilio webhooks

1. https://console.twilio.com/ → **Phone Numbers → Manage → Active numbers** → click your concierge number.
2. **Voice Configuration**:
   - **A call comes in**: Webhook → `https://concierge.appboardbreeze.com/twilio/voice/inbound` → HTTP POST.
   - **Call status changes**: `https://concierge.appboardbreeze.com/twilio/voice/status` → HTTP POST.
3. **Messaging Configuration**:
   - **A message comes in**: Webhook → `https://concierge.appboardbreeze.com/twilio/sms/inbound` → HTTP POST.
4. **Save**.

**Keep a note of the old ngrok URLs** — Phase 11 rollback needs them.

---

## Phase 9 — End-to-end live test on AWS (10 min)

Open `aws logs tail "$LOG_GROUP" --follow --region "$AWS_REGION"` in one terminal. Make these calls/texts from your phone:

1. **Just dial in.** Greeting plays, "Hello! This is the BoardBreeze concierge…"
2. **"How far ahead do I have to post a Brown Act agenda?"** — should cite Gov. Code § 54954.2 and "seventy-two hours."
3. **"How much is the Pro plan?"** — "ninety-nine dollars per month."
4. **"Can I talk to Grace directly?"** — your phone gets a Twilio SMS within ~5 seconds.
5. **Text** "How much is the Pro plan?" — same product KB answer over SMS.
6. **"Goodbye."** — clean farewell + hangup.

If all six pass, you're live in production.

---

## Phase 10 — Iterating on the deploy (push-to-deploy)

ECS doesn't auto-deploy from git the way App Runner does. The standard loop:

```bash
# 1. Make code changes, commit, push
git add . && git commit -m "..." && git push

# 2. Build + push image
GIT_SHA=$(git rev-parse --short HEAD)
ECR_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO"
docker build -t "$ECR_URI:$GIT_SHA" -t "$ECR_URI:latest" .
docker push "$ECR_URI:$GIT_SHA"
docker push "$ECR_URI:latest"

# 3. Register new task def revision pointing at new image
sed "s|$ECR_URI:[a-f0-9]\\{7\\}|$ECR_URI:$GIT_SHA|" /tmp/taskdef.json > /tmp/taskdef.new.json
aws ecs register-task-definition --cli-input-json file:///tmp/taskdef.new.json --region "$AWS_REGION"

# 4. Update service to roll
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
  --task-definition "$TASK_FAMILY" --region "$AWS_REGION"
```

Rolling deploy: ECS spins up the new task, waits for ALB to mark it healthy, then drains the old one. Zero-downtime, ~2 min.

Optional later: a `scripts/deploy.sh` that does steps 2–4 in one shot, and a GitHub Action that runs on `push` to `main`.

---

## Phase 11 — Rollback (~30 seconds)

**Twilio rollback** (fastest — service stays up, just no traffic):

1. Twilio Console → number → set webhooks back to:
   - `https://boardbreeze.ngrok.app/twilio/voice/inbound`
   - `https://boardbreeze.ngrok.app/twilio/voice/status`
   - `https://boardbreeze.ngrok.app/twilio/sms/inbound`
2. Save. Calls instantly land on your laptop again (assuming `ngrok start concierge` + uvicorn are running).

**Service rollback to previous task def** (if a deploy went bad):

```bash
# List recent revisions
aws ecs list-task-definitions --family-prefix "$TASK_FAMILY" --region "$AWS_REGION" \
  --sort DESC --max-results 5

# Roll back to the previous one (e.g., :12 instead of :13)
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
  --task-definition "$TASK_FAMILY:12" --region "$AWS_REGION"
```

`deploymentCircuitBreaker.rollback=true` (set in 7.1) means if a new deploy fails health checks twice, ECS auto-reverts to the previous revision. So most "bad deploy" cases self-heal.

---

## Phase 12 — Post-launch hygiene (do within a day)

- [ ] **Cost budget.** AWS Console → Billing → Budgets → $75/month, email alert at 80%.
- [ ] **CloudWatch alarms** (start simple — one alarm each):
  - Target group `UnHealthyHostCount > 0` for 2 min → email
  - Service `RunningTaskCount < 1` for 2 min → email
  - Task `CPUUtilization > 85%` for 5 min → email
- [ ] **Container Insights.** `aws ecs put-account-setting --name containerInsights --value enabled` for richer per-task metrics.
- [ ] **README update.** Replace ngrok URL with `https://concierge.appboardbreeze.com`.
- [ ] **Image tag retention.** ECR holds every push forever by default — set a lifecycle policy to keep the last 10 tagged + delete untagged after 7 days.
- [ ] **GitHub Action for push-to-deploy.** Makes step Phase 10 a single `git push` again.

---

## Quick reference — when something goes sideways

| Symptom | First thing to check |
|---|---|
| Caller hears Twilio default error tone | ECS task running? `aws ecs list-tasks ...`. Target healthy? `aws elbv2 describe-target-health ...`. If both yes, Twilio webhook URL typo. |
| Greeting plays, then dead air | Likely missing/wrong `ELEVENLABS_API_KEY` in Secrets Manager. Tail logs for KeyError. Update secret + force new deploy. |
| `/health` returns 503 from ALB | Target group has 0 healthy targets. Either task crashed (logs) or task SG doesn't allow ALB SG on 8000 (Phase 6.1). |
| Task definition won't register | Almost always a typo in `valueFrom` ARN or `executionRoleArn`. Re-paste from `echo $SECRET_ARN` / `echo $EXEC_ROLE_ARN`. |
| ECR push: "no basic auth credentials" | Re-run Phase 2.2 (auth tokens are 12-hour TTL). |
| ACM stuck on Pending validation | Vercel CNAME wrong or not propagated. `dig _abcd.concierge.appboardbreeze.com CNAME` — should return the `acm-validations.aws` value. |
| Service stuck "Pending" | ECR pull denied (execution role missing `AmazonECSTaskExecutionRolePolicy`) or subnets have no route to internet (need IGW or NAT). |
| Bill spiked | ALB hourly + LCU charges; or you accidentally bumped `desiredCount` above 1; or CloudWatch logs retention got reset to "Never expire." |
| Want to undo everything | Phase 11 Twilio rollback. To delete: `aws ecs delete-service --force ...`, then ALB, then target group, then ECR repo. Secret + IAM roles cost ~$0. |

---

## Open-loop items to revisit post-submission

- **Push-to-deploy automation** — GitHub Action with OIDC role, no static AWS keys.
- **Auto-scaling** — currently min=max=1. Once Grace has paying customers, set min=1, max=3, scale on `ALBRequestCountPerTarget > 50`.
- **Secrets rotation** — Lambda-based rotation for Anthropic / Twilio tokens once compliance asks.
- **Multi-region failover** — duplicate the stack in `us-west-2`, Route 53 health-check failover. Only worth it at scale.
- **Move the app into the existing `BoardBreezeStack` CDK** — would consolidate ops but adds CDK-learning cost. Defer until comfortable.
