# FlowPilot

**FlowPilot** is a developer-first, **API-driven workflow automation engine**. You define automations as **DAGs** of nodes (HTTP, conditions, transforms, email, delays, restricted code, read-only SQL, webhook responses). Runs are triggered by **webhooks**, **cron schedules** (Celery Beat), or **manual API execution**—similar in spirit to n8n or Zapier, but **backend-only** and **portfolio-friendly**.

**Latest:** AI nodes (`llm_agent`, `ai_crew`) plus **workflow dry-run** (`POST /api/simulate`) that skips side-effect nodes.

---

## Architecture

```
                    +------------------+
                    |    Triggers      |
                    +--------+---------+
                             |
         +-------------------+-------------------+
         |                   |                   |
   +-----v-----+       +------v------+     +------v------+
   |  Webhook  |       |    Cron     |     |   Manual    |
   |  /hooks/* |       |Celery+Beat  |     | POST execute|
   +-----+-----+       +------+------+     +------+------+
         |                    |                    |
         +--------------------+--------------------+
                              |
                      +-------v--------+
                      | WorkflowEngine |
                      |  + interpolation
                      |  + DAG traverse |
                      +-------+--------+
                              |
              +---------------v---------------+
              |         Node executors         |
              +---------------+---------------+
                              |
    +------------+------------+------------+------------+
    |            |            |            |            |
+---v---+   +----v----+  +----v----+  +-----v----+ +-----v-----+
| HTTP  |   |Condition|  |Transform|  |  Email   | |  Delay   |
+-------+   +---------+  +---------+  +----------+ +----------+
    |            |            |            |            |
+---v---+   +----v----+  +-----v---------+
| Code  |   |Database |  |WebhookResponse|
+-------+   +---------+  +---------------+
                              |
                      +-------v--------+
                      | Executions &   |
                      | WorkflowLog    |
                      +----------------+
```

---

## Tech stack

| Layer | Choice |
|--------|--------|
| API | FastAPI |
| ORM | SQLAlchemy 2.x |
| DB | PostgreSQL (SQLite possible for local experiments) |
| Queue | Celery + Redis |
| Scheduler | Celery Beat + `croniter` |
| HTTP nodes | `httpx` |
| Auth | JWT (Bearer), bcrypt passwords |

---

## Repository layout

```
app/
  main.py                 # FastAPI app
  core/                   # config, db session, security, deps
  models/                 # User, Workflow, Execution, Log, Webhook, Schedule, Template
  schemas/                # Pydantic v2 models
  api/routes/             # auth, workflows, executions, webhooks, templates
  services/
    engine.py             # DAG executor + {{ variable }} interpolation
    scheduler.py          # Cron registration / due triggers
    nodes/                  # Node implementations
  tasks/                  # Celery app + workflow + schedule tasks
tests/
```

---

## Workflow definition (JSON)

Workflows store **`nodes`** (array of definitions) and **`edges`** (connections). Each node has at least `id`, `type`, and `config`.

```json
{
  "name": "Demo",
  "trigger_type": "manual",
  "nodes": [
    {
      "id": "http1",
      "type": "http_request",
      "config": {
        "method": "GET",
        "url": "https://api.github.com/repos/octocat/Hello-World",
        "parse_response_as": "json"
      }
    },
    {
      "id": "resp",
      "type": "webhook_response",
      "config": {
        "status_code": 200,
        "body": { "ok": true, "repo": "{{http1.output.body.name}}" }
      }
    }
  ],
  "edges": [
    { "source": "http1", "target": "resp", "condition": "on_success" }
  ]
}
```

---

## Node types

| `type` | Description | Notable `config` keys |
|--------|-------------|------------------------|
| `http_request` | HTTP call with templated URL/headers/body | `method`, `url`, `headers`, `body`, `timeout_seconds`, `parse_response_as`, `fail_on_error` |
| `condition` | Rules → `branch` for routing | `rules` (`operator`: equals, contains, greater_than, regex, exists), `default_branch` |
| `transform` | Map fields, template string, type coercion | `field_map`, `extractions`, `template`, `conversions` |
| `email` | SMTP send | `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `from_address`, `to_addresses`, `subject`, `body`, `html` |
| `delay` | `time.sleep` in worker | `seconds`, `max_seconds` |
| `code` | Restricted `eval` expression | `expression`, `timeout_seconds` (Unix), `max_expression_length` |
| `database` | Read-only `SELECT` | `database_url`, `query`, `max_rows` |
| `webhook_response` | Shape HTTP response for webhook-triggered runs | `status_code`, `headers`, `body` |

---

## Variable interpolation

In string fields inside **`node.config`**, you can reference:

- **Trigger payload:** `trigger.<path>` (e.g. `trigger.body.action` for webhook JSON).
- **Prior node outputs:** `<node_id>.output.<path>` (e.g. `http1.output.body.id`).

Syntax: **`{{trigger.body.issue.title}}`**, **`{{slack_prep.output.text}}`**.

Values that resolve to `dict` / `list` are JSON-serialized when substituted into strings.

---

## Example: “Send Slack on new GitHub issue”

Conceptual workflow (adjust URLs and tokens via env-backed configs in real deployments):

```json
{
  "name": "GitHub issue → Slack",
  "trigger_type": "webhook",
  "nodes": [
    {
      "id": "check",
      "type": "condition",
      "config": {
        "rules": [
          {
            "operator": "equals",
            "left": "trigger.body.action",
            "right": "opened",
            "branch": "new_issue"
          }
        ],
        "default_branch": "ignore"
      }
    },
    {
      "id": "format",
      "type": "transform",
      "config": {
        "merge_input": true,
        "template": "New issue: {{trigger.body.issue.title}} in {{trigger.body.repository.full_name}}"
      }
    },
    {
      "id": "notify",
      "type": "http_request",
      "config": {
        "method": "POST",
        "url": "https://hooks.slack.com/services/XXX/YYY/ZZZ",
        "headers": { "Content-Type": "application/json" },
        "body": {
          "text": "{{format.output.rendered}}"
        }
      }
    },
    {
      "id": "respond",
      "type": "webhook_response",
      "config": {
        "status_code": 200,
        "body": { "accepted": true }
      }
    }
  ],
  "edges": [
    { "source": "check", "target": "format", "branch": "new_issue" },
    { "source": "format", "target": "notify", "condition": "on_success" },
    { "source": "notify", "target": "respond", "condition": "on_success" }
  ]
}
```

Register a **webhook endpoint** for the workflow, set the workflow **active**, and point GitHub’s webhook to `/api/hooks/<path>` with header **`X-FlowPilot-Token`**.

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/auth/register` | Create user (first user becomes `admin`) |
| POST | `/api/auth/login` | OAuth2 password form → JWT |
| GET | `/api/auth/me` | Current user |
| GET | `/api/workflows` | List workflows |
| POST | `/api/workflows` | Create workflow |
| GET | `/api/workflows/{id}` | Get workflow |
| PATCH | `/api/workflows/{id}` | Update |
| DELETE | `/api/workflows/{id}` | Delete |
| POST | `/api/workflows/{id}/execute` | Manual run |
| GET | `/api/workflows/{id}/executions` | Execution history |
| POST | `/api/workflows/{id}/activate` | Activate |
| POST | `/api/workflows/{id}/deactivate` | Deactivate |
| POST | `/api/workflows/{id}/clone` | Clone (+ new webhook rows if applicable) |
| POST | `/api/workflows/{id}/webhook-endpoints` | Register webhook path (response includes `secret_token` once) |
| POST | `/api/workflows/{id}/schedules` | Add cron schedule (`croniter` expression) |
| GET | `/api/executions` | List executions |
| GET | `/api/executions/{id}` | Execution + node logs |
| POST | `/api/executions/{id}/retry` | Re-run with same trigger payload |
| POST | `/api/hooks/{path}` | Incoming webhook trigger |
| GET | `/api/webhook-endpoints` | List webhook endpoints |
| GET | `/api/templates` | List templates |
| POST | `/api/templates` | Create template (optional `workflow_id`) |
| POST | `/api/templates/{id}/use` | Instantiate workflow from template |
| GET | `/health` | Liveness |

OpenAPI: **`/docs`**.

---

## Configuration

Copy **`.env.example`** → **`.env`**. Required:

- `DATABASE_URL`, `REDIS_URL`
- `SECRET_KEY` (≥ 32 chars)
- `WEBHOOK_SECRET` (≥ 16 chars; reserved for signing / future HMAC patterns)

Optional: `CELERY_*`, `MAX_WORKFLOW_STEPS`, `EXECUTION_TIMEOUT_SECONDS`, `LOG_LEVEL`.

**No secrets are hardcoded** in the application source.

---

## Docker

```bash
cp .env.example .env
# edit SECRET_KEY / WEBHOOK_SECRET
docker compose up --build
```

Services: **`api`**, **`worker`**, **`beat`**, **`db`**, **`redis`**.

With `DEBUG=true`, the API process runs `create_all` once at startup (development convenience). Use **Alembic** for real migrations.

---

## Local run

From the project root (so `app` is importable):

```bash
pip install -r requirements.txt
cp .env.example .env
# set variables; for SQLite use DATABASE_URL=sqlite:///./flowpilot.db
uvicorn app.main:app --reload
```

If another project also uses a top-level package named `app`, set `PYTHONPATH` to this repository root explicitly.

---

## Scaling notes

- **Horizontally scale** stateless `api` instances behind a load balancer.
- **Celery workers** scale independently; use **task queues per priority** if needed.
- **PostgreSQL** for durable workflow definitions and execution audit trail.
- **Redis** for broker/backend; consider **Redis Cluster** / **SQS** for large deployments.
- Long-running or high-volume webhook ingress should add **rate limiting** and **idempotency keys** (not included in this portfolio baseline).

---

## CI/CD

This project includes GitHub Actions for continuous integration:

- **Lint**: Code quality checks with `ruff`
- **Test**: Automated test suite with PostgreSQL and Redis services  
- **Build**: Docker image build verification
- **Deploy**: Configurable deployment to AWS ECS/GCP Cloud Run (see `deploy` job in workflow)

## Observability

- **Structured Logging**: JSON-formatted logs with request tracing
- **Health Checks**: `GET /health` with dependency status (database, Redis, external services)
- **Metrics Ready**: Prometheus-compatible metrics endpoint structure
- **Error Tracking**: Structured error responses with correlation IDs

## Cloud Deployment

- **AWS ECS/Fargate**: Stateless API + dedicated worker + beat scheduler
- **AWS RDS**: PostgreSQL for workflow definitions and execution logs
- **AWS ElastiCache**: Redis for Celery broker and result backend
- **AWS SQS**: Alternative queue backend for high-throughput workflows
- **AWS Lambda**: Optional — trigger workflows from AWS events

---

## License

MIT (or replace with your preferred license for your portfolio).
