# FlowPilot — internal maintainer notes (private)

## Run locally

1. `cp .env.example .env` and set `SECRET_KEY`, `WEBHOOK_SECRET`, and DB URLs.
2. `pip install -r requirements.txt`
3. `DEBUG=true` enables `create_all` on startup (development only).
4. `uvicorn app.main:app --reload`

## Celery

- Worker: `celery -A app.tasks.celery_app.celery_app worker -l INFO`
- Beat: `celery -A app.tasks.celery_app.celery_app beat -l INFO`
- Beat runs `check_scheduled_workflows` every minute.

## Docker

- `docker compose up --build`
- API: `http://localhost:8000`, docs: `/docs`.

## Security reminders

- Never commit `.env`.
- Rotate `SECRET_KEY` and webhook endpoint secrets per environment.
- `CodeNode` uses restricted `eval`; Unix gets SIGALRM timeout — Windows relies on expression length cap.
- `DatabaseNode` only allows single `SELECT` statements against user-supplied DSNs — treat as high risk; restrict in production via allowlists.

## Production hardening (not implemented here)

- Alembic migrations instead of `create_all`.
- Rate limiting on `/api/hooks/*`.
- Webhook HMAC using `WEBHOOK_SECRET` in addition to per-endpoint tokens.
- Separate read-only DB role for `DatabaseNode`.
