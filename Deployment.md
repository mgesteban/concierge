# BoardBreeze Concierge — AWS App Runner Deployment Plan

**Goal:** move the Concierge from Grace's laptop (uvicorn + ngrok) to AWS App Runner so it runs 24/7 for real BoardBreeze subscribers, with auto-deploy from GitHub, managed HTTPS, and predictable monthly cost.

**Why App Runner over alternatives:** managed (no OS to patch), Python 3.11 native runtime (no Docker drift to debug), GitHub-connected (push-to-deploy), auto-renewing TLS, predictable price. EC2/Lightsail VM means we manage the OS; Lambda doesn't fit the chained-TwiML voice flow (background threads + futures). App Runner is the tightest fit.

**Estimated total time:** 60–90 minutes the first time. Most of it is AWS console clicks; code changes are ~15 minutes.
**Estimated monthly cost:** ~$30–35 for App Runner at 1 vCPU / 2 GB, min=1 instance always-on (you can't do telephony with cold-start scaling). Plus your existing Supabase / Voyage / Anthropic / Twilio / ElevenLabs costs (unchanged).
**Rollback path:** if anything goes wrong post-deploy, point Twilio webhooks back at `https://boardbreeze.ngrok.app` (your laptop) — your local stack still works exactly as before. Two clicks in Twilio Console, ~30 seconds.

---

## Pre-flight checklist (5 minutes)

Confirm before we start. Each item should be a "yes" — if any is "no," stop and fix that first.

- [ ] **AWS account access.** You can sign in to https://console.aws.amazon.com/ as either root or an IAM user with `AdministratorAccess` (we'll narrow this later).
- [ ] **AWS region picked.** Use **us-west-2 (Oregon)** — closest big region to Oakland, App Runner fully supported there.
- [ ] **GitHub access.** You can sign in to https://github.com/mgesteban/concierge and you're an admin on that repo.
- [ ] **Local repo is on `main` and clean.** Run `git status` — should say "nothing to commit." If not, commit or stash first. We'll be pushing changes to GitHub for App Runner to build from.
- [ ] **Current `.env` is complete and working.** Recent test calls confirm Anthropic, Supabase, Voyage, Twilio, ElevenLabs, and Grace's phone all work. We'll copy the *values* into App Runner's env-var config, but the local file stays gitignored as always.
- [ ] **Twilio Console access.** You can sign in to https://console.twilio.com/ and edit the webhook URLs on your concierge phone number.

---

## Phase 0.5 — Update the live CMA agent so SMS sees `search_product_kb` (10 min)

**Why this happens before the AWS work, not after:**

The CMA agent created Thursday is locked to its original tool list (no `search_product_kb`). Voice loads tools fresh per turn, so voice already has it; SMS doesn't until we explicitly update. The Anthropic SDK supports `agents.update()` with the tools + system fields, which preserves the agent_id and every existing session in `phone_sessions` — so cross-session memory ("Jane texts Monday, again Thursday") survives the upgrade. Doing this before App Runner means production launches with full feature parity from the very first SMS.

### 0.5.1 Run the update script

I've added `scripts/update_cma_agent.py`. It does three things: finds the agent named `boardbreeze-concierge` in your Anthropic account, reads its current version, and calls `update()` with today's `CUSTOM_TOOLS` + `SYSTEM_PROMPT`. No agent_id change. No session loss.

```bash
cd /home/grace/boardbreeze-concierge-voice
.venv/bin/python -m scripts.update_cma_agent
```

**Expected output:**

```
Found agent: name='boardbreeze-concierge' id=agent_011CaMckX2etSZait4iM4kfi version=N
  Before — tools: ['search_governance_kb', 'verify_citation', 'escalate_to_grace']
  After  — tools: ['search_governance_kb', 'search_product_kb', 'verify_citation', 'escalate_to_grace'] version=N+1
Done. Existing CMA sessions preserved (agent_id unchanged).
```

If you see "No live agent found": that means the agent was archived or never created — boot the app once locally, then re-run this script.

### 0.5.2 Smoke-test SMS against the local stack

Send an SMS to your Twilio concierge number from your personal phone:

> **You text:** *"How much is the Pro plan?"*
> **Expected reply:** mentions "$99 per month" or "ninety-nine dollars per month" — *and* the demo log feed (`./scripts/demo_log.sh`) shows `🛒 product KB` firing. If it still dodges with "let me have Grace call you back," the update didn't take and we debug before moving on.

> **You text:** *"How far ahead do I have to post a Brown Act agenda?"*
> **Expected reply:** cites § 54954.2 / 72 hours. Confirms governance still works.

If both pass, SMS is at full feature parity. Continue to Phase 1.

---

## Phase 1 — Add deployment files to the repo (5 min)

We add three small files. None contain secrets. All commit to git so App Runner can read them on every deploy.

### 1.1 `apprunner.yaml`

Tells App Runner how to build and run the app — Python 3.11, install requirements, start uvicorn on port 8000. **Already written and on disk** at the repo root:

```yaml
version: 1.0
runtime: python311
build:
  commands:
    build:
      - pip install --no-cache-dir -r requirements.txt
run:
  command: uvicorn app.main:app --host 0.0.0.0 --port 8000
  network:
    port: 8000
```

**Decisions baked in:**
- `--host 0.0.0.0`, not `127.0.0.1`. Containers need to bind on all interfaces so App Runner's load balancer can reach the process.
- Port 8000 (matches local dev). App Runner's `network.port` tells the platform which port to forward traffic to.
- No env vars hardcoded here — secrets go via the App Runner Console (Phase 4.4).
- No `.dockerignore` / `.gitattributes` — App Runner pulls from GitHub, so the existing `.gitignore` already keeps personal files (`Questions.md`, `video_script.md`, the FAQ, the AALRR PDF) out of the build context. Nothing extra to ship.

### 1.2 Sanity-test the start command locally

After I write `apprunner.yaml`, we test the production start command on your machine to make sure nothing's broken before we push:

```bash
# Stop the current --reload uvicorn (Ctrl+C in its terminal) and run
# the production-style command instead:
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# Confirm /health responds:
curl -s http://127.0.0.1:8000/health
# expected: {"status":"ok"}
```

If that returns `{"status":"ok"}`, we're good. Stop it and resume the `--reload` version for development.

---

## Phase 2 — Commit & push to GitHub (5 min)

```bash
git add apprunner.yaml scripts/update_cma_agent.py
git status                        # confirm only the two new files staged
git diff --cached                  # review what's about to ship
git commit -m "feat(deploy): App Runner config + CMA agent update script"
git push origin main
```

Verify on https://github.com/mgesteban/concierge that both files are present.

---

## Phase 3 — Connect AWS to your GitHub repo (10 min)

This is a one-time OAuth handshake. App Runner installs a small AWS-managed GitHub App on your repo so it can pull source on every push.

1. Sign in to AWS Console: https://console.aws.amazon.com/
2. **Top-right region selector** → choose **US West (Oregon) us-west-2**.
3. Search bar (top center) → type **App Runner** → click the result.
4. Left nav → **GitHub connections** → click **Add new**.
5. **Connection name:** `boardbreeze-github` (anything works; this is just a label).
6. Click **Install new** under "GitHub app." A GitHub OAuth window opens.
7. In GitHub: choose **mgesteban** as the account. **Repository access:** "Only select repositories" → pick `concierge`. Click **Install & Authorize**.
8. Back in AWS: the connection appears with status **Pending handshake** for a few seconds, then **Available**. Click **Complete handshake** if AWS prompts you.
9. Done. AWS can now read your `concierge` repo to build from.

---

## Phase 4 — Create the App Runner service (15 min)

Now the actual service. This is the longest phase but it's all clicks and form fills.

### 4.1 Start the create-service flow

1. App Runner Console → **Services** → **Create service**.

### 4.2 Source

- **Repository type:** Source code repository.
- **Connect to source code repository:**
  - Provider: GitHub
  - Connection: `boardbreeze-github` (the one from Phase 3)
  - Repository: `mgesteban/concierge`
  - Branch: `main`
  - Source directory: `/` (default — leave blank).
- **Deployment trigger:** **Automatic** (so future `git push origin main` auto-deploys).
- Click **Next**.

### 4.3 Build settings

- **Configuration file:** **Use a configuration file** (uses our `apprunner.yaml` from Phase 1).

  *If you accidentally pick "Configure all settings here" instead, the same values can be entered in the form — runtime: Python 3.11, build command: `pip install --no-cache-dir -r requirements.txt`, start command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`, port: 8000.*

- Click **Next**.

### 4.4 Service settings

This is the longest single screen. Take it slow.

- **Service name:** `boardbreeze-concierge` (becomes part of the URL).
- **Virtual CPU & memory:** **1 vCPU**, **2 GB** memory. *(0.5 vCPU / 1 GB is cheaper but may be tight for the voice pipeline's threading; 1/2 is the safe default for telephony workloads.)*
- **Environment variables — Plain text** (we'll paste 9 values; **none of these go in git**, they live in App Runner only):

  | Key                       | Value (copy from your local `.env`) |
  |---------------------------|-------------------------------------|
  | `ANTHROPIC_API_KEY`       | `sk-ant-…`                          |
  | `SUPABASE_URL`            | `https://YOUR-PROJECT.supabase.co`  |
  | `SUPABASE_SERVICE_KEY`    | `eyJhbGc…`                          |
  | `VOYAGE_API_KEY`          | `pa-…`                              |
  | `TWILIO_ACCOUNT_SID`      | `AC…`                               |
  | `TWILIO_AUTH_TOKEN`       | `…`                                 |
  | `TWILIO_PHONE_NUMBER`     | `+1XXXXXXXXXX`                      |
  | `ELEVENLABS_API_KEY`      | `…`                                 |
  | `ELEVENLABS_VOICE_ID`     | `…` (your locked voice — do not change) |
  | `GRACE_PHONE_NUMBER`      | `+1XXXXXXXXXX`                      |
  | `GRACE_EMAIL`             | `mesteban@ccsf.edu`                 |

  *Tip: open `.env` locally with a text editor on the side. Copy each value with the `=` sign already removed; AWS asks for key + value separately.*

  *Optional later: move secrets to AWS Secrets Manager. Not required for launch.*

- **Port:** `8000` (matches `apprunner.yaml`).
- **Auto-deployments:** keep **enabled** (already set in Phase 4.2).
- **Health check:** click **Configure** → set:
  - Protocol: **HTTP**
  - Path: `/health`
  - Interval: 10 seconds
  - Timeout: 5 seconds
  - Healthy threshold: 1
  - Unhealthy threshold: 3
- **Auto-scaling:** click **Configure** → **Add custom configuration**.
  - Name: `concierge-fixed-1`
  - **Max concurrency:** 100
  - **Max size:** **1**
  - **Min size:** **1**
  - *(Min=Max=1 means exactly one always-on instance. Predictable cost, no cold-start latency. We can scale up later when call volume grows.)*
- **Security:** leave defaults (App Runner managed VPC).
- **Networking:** leave defaults (public endpoint).
- **Observability:** turn **on** "AWS X-Ray active tracing" (free for the first 100k traces/mo, helpful for debugging latency spikes).
- **Tags:** optional — can add `project=boardbreeze`, `env=prod` for billing reports.
- Click **Next**.

### 4.5 Review and create

- Skim the summary screen — it will list everything from 4.2–4.4.
- Click **Create & deploy**.
- AWS shows "Service status: Operation in progress." First build takes **5–10 minutes** (`pip install` is the slow part).

### 4.6 Watch the build

- Click into the new service → **Logs** tab → **Application logs** — empty until first run.
- **Events** tab — shows build progress (Pulling source → Building → Provisioning → Starting → Running).
- Once status flips to **Running** in green, App Runner shows the **Default domain** at the top of the service page. It looks like:
  `https://abc123def456.us-west-2.awsapprunner.com`
- **Copy that URL.** This is your new public base URL.

---

## Phase 5 — Smoke-test App Runner before flipping Twilio (5 min)

We test the App Runner URL directly first, *before* changing Twilio. This way if anything's broken, the production phone number still works (still pointing at ngrok).

```bash
# Replace APPRUNNER_URL with the URL from Phase 4.6.
APPRUNNER_URL="https://abc123def456.us-west-2.awsapprunner.com"

curl -s "$APPRUNNER_URL/health"
# expected: {"status":"ok"}

curl -s "$APPRUNNER_URL/"
# expected: {"service":"BoardBreeze Concierge","status":"live","repo":"…"}
```

**If `/health` is 200:** great — App Runner is serving the live build. Continue.

**If `/health` is 502 or never responds:**
- Check **Logs → Application logs** in App Runner Console. Look for a Python traceback.
- Most common causes: missing env var (e.g. `ANTHROPIC_API_KEY` absent → app crashes on first import), or a typo in `apprunner.yaml`.
- Fix the env var in **Configuration → Environment variables → Edit**, save, and App Runner redeploys (~3 minutes).

---

## Phase 6 — Update Twilio webhooks (5 min)

This is the cutover. After this step, real callers reach AWS instead of your laptop.

1. Sign in to https://console.twilio.com/.
2. Left nav → **Phone Numbers** → **Manage** → **Active numbers**.
3. Click your concierge number (the one subscribers call).
4. Under **Voice Configuration:**
   - **A call comes in:** Webhook → URL: `{APPRUNNER_URL}/twilio/voice/inbound` → HTTP POST.
   - **Call status changes:** URL: `{APPRUNNER_URL}/twilio/voice/status` → HTTP POST.
5. Under **Messaging Configuration:**
   - **A message comes in:** Webhook → URL: `{APPRUNNER_URL}/twilio/sms/inbound` → HTTP POST.
6. Click **Save** at the bottom.

*Replace `{APPRUNNER_URL}` with the App Runner URL from Phase 4.6 (https://abc123def456…awsapprunner.com).*

**Keep a copy of the old ngrok webhook values somewhere** — for the rollback step in Phase 8, you'll need them.

---

## Phase 7 — End-to-end live test on AWS (10 min)

Now the real test: dial the number, talk to the AI, confirm everything still works.

Open the App Runner **Logs → Application logs** in one browser tab so you can watch live (it's a CloudWatch tail with a delay of a few seconds).

Run a tight version of the `Questions.md §0` smoke set:

1. **Just dial in.** Confirm: greeting plays, starts with "Hello! This is the BoardBreeze concierge…". *(Logs should show: `tts static-cached greeting (NNNN bytes)` then a `POST /twilio/voice/inbound` 200.)*
2. **"How far ahead do I have to post a Brown Act agenda?"** — should cite Gov. Code § 54954.2 and "seventy-two hours." *(Logs: `match_governance_kb` RPC, `voice_pipeline: synth sentence` lines.)*
3. **"How much is the Pro plan?"** — should say "ninety-nine dollars per month" cleanly.
4. **"Can I talk to Grace directly?"** — your phone should get a Twilio SMS within ~5 seconds.
5. **"Goodbye."** — clean farewell + hangup, no "let me take a quick look" filler.

If all five pass, you're live in production.

---

## Phase 8 — What to do if something breaks (rollback, ~30 seconds)

Twilio rollback is two clicks. Whenever you need to test something local-only, or if AWS misbehaves at an inconvenient time:

1. Twilio Console → your number → set the three webhook URLs back to:
   - Voice "A call comes in": `https://boardbreeze.ngrok.app/twilio/voice/inbound`
   - Voice "Call status changes": `https://boardbreeze.ngrok.app/twilio/voice/status`
   - Messaging "A message comes in": `https://boardbreeze.ngrok.app/twilio/sms/inbound`
2. Save. New calls instantly go to your laptop again (assuming uvicorn + ngrok are running).

App Runner stays up regardless — rolling Twilio back doesn't tear down AWS. You're paying for it whether traffic flows or not, until you delete the service.

---

## Phase 9 — Post-launch hygiene (15 min, can do tomorrow or Monday)

These aren't blocking — the service works without them — but worth doing within a day or two.

### 9.1 Re-provision the CMA agent so SMS sees `search_product_kb`

The existing CMA agent (`agent_011CaMckX2etSZait4iM4kfi`) was created Thursday with the old tool roster. Voice picks up new tools automatically; SMS doesn't. We have two choices:

- **A. Use `c.beta.agents.update(agent_id, …)`** if the SDK supports it. *Check the Anthropic SDK docs.*
- **B. Archive the old agent + let `ensure_agent()` create a fresh one with today's tool list.** Simpler. Existing SMS sessions will still resolve to the new agent on next message.

Either way, ~10 minutes of work and a one-line confirmation that SMS now retrieves product KB content.

### 9.2 Custom domain (optional)

Replace `abc123def456.us-west-2.awsapprunner.com` with `concierge.appboardbreeze.com` so the URL on dashboards / docs / logs reads cleanly.

In App Runner Console → service → **Custom domains** → **Link domain** → enter `concierge.appboardbreeze.com`. AWS prints DNS records (a `CNAME` and two cert-validation `CNAME`s). Add them at your domain registrar. Cert provisioning takes ~10 minutes. Then update Twilio one more time to use the custom domain.

### 9.3 CloudWatch logging budget

App Runner pipes logs to CloudWatch with a 30-day retention default. Check **CloudWatch → Log groups → /aws/apprunner/boardbreeze-concierge/...** — confirm retention is 30 days (not "Never expire"). Logs are tiny but "Never expire" silently grows your bill.

### 9.4 Cost alarm

AWS Console → **Billing → Budgets → Create budget** → cost budget, $50/month, email alert at 80%. One safety net so the bill never surprises you.

### 9.5 Update README

Replace the ngrok URL in `README.md` setup section with the App Runner URL (and/or your custom domain once 9.2 is done).

### 9.6 Optional: move secrets to AWS Secrets Manager

For now, env vars are stored as encrypted-at-rest plain values in App Runner. That's fine for launch. If you ever rotate the Anthropic key or Twilio token, doing it via Secrets Manager (App Runner has a built-in integration) means you change it in one place rather than touching each env var in the App Runner config. Worth doing once you're comfortable with the AWS console.

---

## Phase 10 — What to monitor in the first week

Daily for the first 5 days, then weekly:

- **App Runner → Metrics tab**: CPU/memory utilization, request latency, instance count. If CPU pegs at 100% during a call, bump to 2 vCPU.
- **App Runner → Logs**: any Python tracebacks? Any 500s?
- **Twilio Console → Monitor → Logs → Calls**: any calls ending in `failed` or `no-answer`? (compare to ngrok-era baseline)
- **Anthropic console → Usage**: making sure prompt caching is working and we're not burning Opus tokens unnecessarily.
- **Supabase → Database → Query performance**: governance_kb pgvector queries should still be <100ms.

If nothing alarms after a week, the deploy is stable.

---

## Quick reference — when something goes sideways

| Symptom | First thing to check |
|---------|----------------------|
| Caller hears Twilio default error tone | App Runner is down, OR webhook URL is wrong. Hit `/health` directly. If 200, fix Twilio URLs. If non-200, check App Runner logs. |
| Greeting plays, then dead air after caller speaks | ElevenLabs API key may be missing/wrong in App Runner env vars. Logs will show `KeyError: 'ELEVENLABS_API_KEY'`. |
| "Sorry, I'm having trouble pulling that up" | Background turn timed out (>12s). Most likely cause: cold Anthropic call after instance idle. Should self-heal on next call. If persistent, check Anthropic API status. |
| `/health` returns 502 from App Runner URL | App is crashing on import. Check **Logs → Application logs** for traceback. Usually a missing env var. |
| App Runner says "Configuration is invalid" before first build | `apprunner.yaml` syntax error. Re-validate locally before pushing. |
| Build hangs at "Pulling source" >5 min | GitHub connection lost. Re-do Phase 3.6–3.8. |
| Cost spikes unexpectedly | Auto-scaling went above min=1 (shouldn't if max=1). Or X-Ray traces exceeded free tier. Check Billing dashboard. |
| Want to undo everything | Phase 8 rollback. App Runner service can also be **paused** (no charges) or **deleted** entirely from the service page. |

---

## Open questions before we start

1. **Service name** — `boardbreeze-concierge` OK, or different? It becomes part of the auto-generated AWS URL until you add a custom domain.
2. **Region** — confirming us-west-2 (Oregon)?
3. **Custom domain** — do Phase 9.2 today, or punt to Monday after submission? Adds ~30 min to the deploy.
4. **CMA agent re-provisioning (Phase 9.1)** — today or Monday?

Once those are answered, we start at Phase 1.
