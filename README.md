# Task Management API

A REST API for managing tasks within projects, built for the Backend Developer (Python) technical assessment. Beyond the base CRUD requirement, this implementation adds a full authentication subsystem (registration, email verification, login, forgot/reset password) with Redis-backed brute-force protection, since the brief calls for exactly that.

The full architecture, schema, and design rationale live in [`task-management-api-design-document.md`](./task-management-api-design-document.md) -- that document was written *before* any code and is the authoritative spec this implementation follows. This README is the "how to run it" companion; see that document for the "why it's built this way" deep dive.

## Tech stack

- **FastAPI** (async) on Python 3.12
- **PostgreSQL** via SQLAlchemy 2.0 (async) + Alembic migrations
- **Redis** for email verification/password reset tokens and login-lockout state
- **Argon2id** password hashing, **JWT** access/refresh tokens
- **Gmail SMTP** for outbound email, behind a swappable `EmailSender` interface
- **pytest** (unit / integration / API tiers), **Docker** + **docker-compose**

## Project structure

Modular monolith: one deployable service, divided into modules by domain (`auth`, `projects`, `tasks`, `notifications`), each following `router -> service -> repository -> model`. See Section 5 of the design doc for the full rationale.

```
app/
  core/          # config, DB session, Redis client, logging, security utils
  common/        # shared exceptions, pagination, base repository, deps
  auth/          # register, verify, login, refresh, logout, forgot/reset password
  projects/      # project CRUD
  tasks/         # task CRUD, filtering, search
  notifications/ # email sending (Gmail SMTP behind an interface)
alembic/         # migrations
tests/
  unit/          # services against in-memory fakes, no DB/Redis
  integration/   # real Postgres + Redis, one rolled-back transaction per test
  api/           # full request/response cycle via httpx.AsyncClient
```

## Prerequisites

- Docker + Docker Compose (quick start), **or** Python 3.12 + a local PostgreSQL 16 and Redis 7 (bare-metal alternative)
- A Gmail account with an App Password, if you want real verification/reset emails to send (optional -- see [Email delivery](#email-delivery))

## Quick start (Docker Compose)

```bash
git clone https://github.com/ushashir/task-mgt-app.git
cd task-mgt-app
cp .env.example .env
docker compose up -d --build
```

This starts three containers -- `api`, `db` (Postgres 16), `redis` (Redis 7) -- and the `api` container runs `alembic upgrade head` before starting the server. Once it's up:

- API: http://localhost:8000
- Swagger UI: **http://localhost:8000/api-docs**
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

> **Port note:** `docker-compose.yml` maps Postgres to host port **5434** (not 5432) and Redis to **6381** (not 6379), specifically to avoid clashing with a Postgres/Redis instance you might already have running locally. The `api` container always reaches them internally as `db:5432` / `redis:6379` regardless of the host-side mapping.

To stop everything (and remove the Postgres volume, i.e. wipe the local dev database):

```bash
docker compose down -v
```

## Bare-metal setup (alternative)

```bash
git clone https://github.com/ushashir/task-mgt-app.git
cd task-mgt-app
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # includes requirements.txt

cp .env.example .env
# edit .env: DATABASE_URL and REDIS_URL must point at Postgres/Redis instances
# you're running yourself (Docker, Homebrew, whatever) -- see below.

alembic upgrade head
uvicorn app.main:app --reload
```

You need your own running PostgreSQL 16 and Redis 7 for this path (e.g. `brew services start postgresql@16` / `redis-server`, or run just the `db`/`redis` services from `docker-compose.yml` with `docker compose up -d db redis`).

## Environment variables

All configuration loads through a single Pydantic `Settings` object (`app/core/config.py`) -- nothing is hardcoded anywhere else in the app. `.env.example` ships with every key below and a placeholder value; `.env` itself is gitignored.

| Variable | Example | Purpose |
|---|---|---|
| `ENVIRONMENT` | `local` / `staging` / `production` | Toggles debug behaviour, log verbosity |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@localhost:5432/taskdb` | Postgres connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection for tokens, lockouts |
| `JWT_SECRET_KEY` | *(random 64-char secret)* | Signs access/refresh tokens |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `LOGIN_MAX_ATTEMPTS` | `5` | Failed logins before lockout |
| `LOGIN_LOCKOUT_MINUTES` | `15` | Lockout duration after threshold is hit |
| `EMAIL_VERIFICATION_TTL_HOURS` | `24` | Verification token lifetime in Redis |
| `PASSWORD_RESET_TTL_MINUTES` | `30` | Reset token lifetime in Redis |
| `GMAIL_USER` | `yourapp@gmail.com` | Sending account |
| `GMAIL_APP_PASSWORD` | *(16-char app password)* | Gmail App Password, **never** the real account password |
| `MAIL_FROM_NAME` | `Task Manager` | Friendly sender name |
| `FRONTEND_URL` | `http://localhost:3000` | Base URL used to build verification/reset links |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

Generate a real `JWT_SECRET_KEY` with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Email delivery

Verification and password-reset emails send through a personal Gmail account via SMTP, using an **App Password**:

1. Enable 2-Step Verification on the Gmail account.
2. Google Account -> Security -> App passwords -> generate one scoped to "Mail".
3. Set `GMAIL_USER` and `GMAIL_APP_PASSWORD` in `.env` to that address and generated password.

If you don't configure real Gmail credentials, registration/forgot-password still work -- the SMTP failure is caught and logged (never raised, never leaks credentials to logs), and you can grab the verification/reset token directly from Redis for local testing:

```bash
redis-cli --scan --pattern 'email_verify:*'   # or 'pwd_reset:*'
redis-cli get 'email_verify:<token-from-above>'   # -> the user id it belongs to
```

## Migrations

```bash
alembic upgrade head              # apply all migrations
alembic revision --autogenerate -m "description"   # generate a new one after changing models
alembic downgrade -1              # roll back one revision
```

### Seeding sample data

There's no dedicated seed script -- seed data through the API itself, either via Swagger UI (`/api-docs`) or curl:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"Str0ng!Pass1","full_name":"Demo User"}'

# grab the verification token from Redis (see Email delivery above) and verify:
curl -X POST http://localhost:8000/api/v1/auth/verify-email \
  -H 'Content-Type: application/json' -d '{"token":"<token>"}'

# log in, then use the access token for everything else:
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"Str0ng!Pass1"}'
```

## API endpoints

Full interactive documentation (request/response schemas, try-it-out): **`/api-docs`** (Swagger UI) or `/redoc`.

**Auth** (`/api/v1/auth`)

| Method | Path | Description |
|---|---|---|
| POST | `/register` | Create an account (unverified) |
| POST | `/verify-email` | Verify email with the token from the verification link |
| POST | `/login` | Log in; locks out after `LOGIN_MAX_ATTEMPTS` failures |
| POST | `/refresh` | Exchange a refresh token for a new token pair (rotates it) |
| POST | `/logout` | Revoke a refresh token |
| POST | `/forgot-password` | Request a reset link (same response whether or not the email exists) |
| POST | `/reset-password` | Reset password with the token from the reset link |
| GET | `/me` | Current authenticated user |

**Projects** (`/api/v1/projects`, all require `Authorization: Bearer <access_token>`)

| Method | Path | Description |
|---|---|---|
| POST | `/` | Create a project |
| GET | `/` | List your projects (paginated) |
| GET | `/{project_id}` | Get a project |
| PATCH | `/{project_id}` | Partially update a project |
| DELETE | `/{project_id}` | Soft-delete a project (cascades to its tasks) |

**Tasks** (`/api/v1/tasks`, all require authentication)

| Method | Path | Description |
|---|---|---|
| POST | `/` | Create a task in one of your projects |
| GET | `/` | List tasks -- paginated, filterable by `status`, `priority`, `project_id`, and free-text `search` across title+description |
| GET | `/{task_id}` | Get a task |
| PATCH | `/{task_id}` | Partially update a task |
| DELETE | `/{task_id}` | Soft-delete a task |

**Other**

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Checks DB + Redis connectivity |

A project or task that exists but belongs to someone else returns `404`, identical to one that doesn't exist at all -- resource IDs aren't enumerable through the API's response codes.

## Testing

Three tiers (`tests/unit`, `tests/integration`, `tests/api`), selected via pytest markers:

```bash
pytest -m unit             # fast, no DB/Redis needed at all
pytest -m integration      # needs real Postgres + Redis (see below)
pytest -m api               # needs real Postgres + Redis (see below)
pytest                      # everything, with the coverage gate
```

The integration/API tiers read `DATABASE_URL`/`REDIS_URL` from your environment exactly like the app does -- point them at disposable instances before running, e.g.:

```bash
docker run -d --name taskdb-test -e POSTGRES_USER=taskuser -e POSTGRES_PASSWORD=taskpass \
  -e POSTGRES_DB=taskdb_test -p 55432:5432 postgres:16-alpine

# in .env (or exported):
DATABASE_URL=postgresql+asyncpg://taskuser:taskpass@localhost:55432/taskdb_test
REDIS_URL=redis://localhost:6379/1   # a distinct Redis DB index, not your dev one

alembic upgrade head   # against the test DB
pytest -m "integration or api"
```

Coverage is gated at 80% (currently ~92%), chased on the service/core layers -- routers, ORM models, and schemas are declarative and excluded, per the design doc's reasoning that they're not worth chasing coverage on.

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on every push/PR to `main` and `dev`:

1. **Lint, format, type-check, unit tests** -- ruff, `black --check`, `isort --check-only`, mypy (strict), then the unit tier. No services needed, runs first.
2. **Integration + API tests** -- real Postgres 16 + Redis 7 as service containers, migrations applied, then the integration and API tiers with the coverage gate.
3. **Docker build check** -- confirms the image builds cleanly on every push/PR, without pushing.
4. **Publish to GHCR** -- only on a push (not a PR) to `dev` or `main`: `dev` publishes `ghcr.io/ushashir/task-mgt-app:dev` (+ `:dev-<sha>`), `main` publishes `:latest` (+ `:prod-<sha>`).

## Branching and deployment model

- `main` = production, `dev` = staging. `main` has GitHub branch protection enabled: PRs required, no direct pushes (including for the repo owner), no force-push. See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full workflow.
- Every push to `dev`/`main` publishes a versioned image to GHCR (see CI/CD above) -- that part of continuous delivery works today.
- **Actually deploying that image to a live hosting platform is not wired up yet.** The original plan (see the design doc's Section 18) was Render or Railway; that's since changed to a platform called Softkloud, but at the time of writing this repo doesn't yet have working details on Softkloud's deployment mechanism (webhook URL, CLI, env var configuration, etc.) to automate against, so this step is intentionally left manual/pending rather than guessed at. Once that's sorted, the missing piece is a final job in `ci.yml` that triggers a deploy after `publish-to-ghcr` succeeds.

## Assumptions

- A **Project** entity was added even though it isn't in the assessment's explicit field list, because tasks are described as living "within a project."
- Multi-tenancy (a project shared by a team) is out of scope -- each project belongs to exactly one user.
- Password policy (8+ characters, upper/lowercase, digit, special character) was added per an explicit requirement beyond the original design doc, enforced in `app/auth/schemas.py`.
- Email addresses are normalized to lowercase and stored as `varchar` rather than requiring the Postgres `citext` extension, to keep the local/Docker setup dependency-free.

## Known limitations

- No live deployment yet (see [Branching and deployment model](#branching-and-deployment-model) above).
- No `restore` endpoint for a soft-deleted project/task, despite `deleted_at` being in the schema -- a reasonable bonus feature that wasn't implemented in the time available.
- Gmail's ~500 messages/day sending limit is fine for this assessment's scale but not a production volume; the `EmailSender` interface (`app/notifications/email_sender.py`) exists specifically so a transactional provider (SES, Postmark, Resend) can replace `GmailSMTPSender` without touching any calling code.
- No dedicated seed script -- see [Seeding sample data](#seeding-sample-data).
