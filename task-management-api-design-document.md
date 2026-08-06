# Task Management System REST API
## Technical Design Document

**Prepared for:** Backend Developer (Python) Technical Assessment
**Prepared by:** Ushahemba Shir
**Deadline:** 9 August 2026, 5:00 PM (WAT)

---

## 1. Purpose and Scope

This document defines the architecture, technology choices, data model, and delivery process for the Task Management System API before any code is written. It exists to remove ambiguity up front, keep the implementation aligned with SOLID and DRY principles, and give a clear story to walk the reviewers through during the technical discussion.

The assessment's stated functional scope is CRUD on tasks (title, description, status, priority, due date, created at). This document extends that scope with a project entity (since tasks are described as living "within a project") and a full authentication subsystem, since the brief calls for login, registration, forgot password, and reset password with Redis-backed rate limiting and email verification.

---

## 2. Stack Recommendation: FastAPI vs Django REST Framework

| Criterion | FastAPI | Django REST Framework |
|---|---|---|
| Async support | Native, first-class (ASGI) | Improving, but ORM is still primarily sync unless using Django 4+ async views carefully |
| Performance | Very high throughput, low overhead | Heavier, more middleware overhead |
| Validation | Pydantic, type-hint driven, minimal boilerplate | DRF serializers, more verbose but mature |
| Batteries included (auth, admin, ORM) | None out of the box, must be assembled | Auth, admin panel, ORM, migrations all included |
| API documentation | Automatic OpenAPI/Swagger and ReDoc generated from type hints | Requires drf-spectacular or drf-yasg |
| Fit for modular monolith / clean architecture | Very natural: routers, dependency injection, and services map cleanly to layered architecture | Possible, but Django's app-centric structure encourages coupling to the ORM unless deliberately layered |
| Learning curve for reviewers | Lower, code reads close to plain Python | Higher, "the Django way" has more implicit behaviour |

**Recommendation: FastAPI.**

The deciding factors are:

1. **Redis-native rate limiting and lockout logic** is easiest to express as explicit dependency-injected services in FastAPI, rather than being retrofitted onto Django's request/response cycle.
2. **Separation of concerns** is a stated requirement. FastAPI does not impose an ORM-centric "fat model" pattern, so a clean layered structure (routers to services to repositories to models) is the natural default rather than something fought for against the framework.
3. **Automatic OpenAPI generation** satisfies the bonus "API documentation (Swagger)" requirement with no extra library.
4. **Async I/O** benefits the auth flows described below, which involve several I/O-bound steps per request (DB lookup, Redis check, email dispatch).

Django REST Framework remains a reasonable second choice if the team already standardises on Django elsewhere (admin panel value, mature ecosystem). That trade-off is noted here for completeness so it can be defended if asked.

---

## 3. Database Recommendation: SQLite vs PostgreSQL vs MySQL

| Criterion | SQLite | MySQL | PostgreSQL |
|---|---|---|---|
| Concurrency | Poor under concurrent writes (file-level locking) | Good | Good, generally stronger under mixed read/write load |
| Data types | Limited (no native ENUM, weak JSON support) | ENUM supported, JSON supported | Native ENUM, robust JSONB, array types |
| Constraints and integrity | Basic | Good | Strongest (check constraints, partial indexes, deferred constraints) |
| Production readiness | Best for local dev/tests only | Production-ready | Production-ready, preferred for new services with evolving schemas |
| Ecosystem fit with SQLAlchemy/Alembic | Fine for dev | Fine | Best migration and indexing support |

**Recommendation: PostgreSQL** for the running application, with **SQLite** used only for fast local unit tests where a real Postgres instance is not spun up.

Reasoning: task `status` and `priority` are natural enums, and PostgreSQL enforces these at the database level rather than only in application code, which reduces one whole class of data integrity bugs. It also has the best long-term story if the system grows (full-text search on task titles/descriptions, JSONB for flexible metadata later, better concurrent write behaviour for a multi-user task board).

---

## 4. Requirements Breakdown

### 4.1 Functional Requirements

- Users can register, verify their email, log in, log out, request a password reset, and reset their password.
- Authenticated users can create, list, retrieve, update, and delete tasks.
- Tasks belong to a project; projects belong to a user (or, later, a team).
- Task fields: title, description, status (To Do, In Progress, Done), priority (Low, Medium, High), due date, created at, updated at.
- Listing tasks supports pagination, filtering (by status, priority, project) and search (by title/description) as bonus features.

### 4.2 Non-Functional Requirements

- **Security:** passwords hashed with a slow hash (Argon2 or bcrypt), JWT access/refresh tokens, short-lived access tokens, brute-force protection on login.
- **Reliability:** consistent error format across all endpoints, no unhandled exceptions leaking stack traces.
- **Performance:** sub-200ms typical response time for CRUD endpoints under light load; Redis used to avoid repeated expensive lookups (e.g., login attempt counters).
- **Observability:** structured logging with request correlation IDs, log levels separating operational noise from actionable errors.
- **Maintainability:** modular monolith structure, dependency inversion between layers, one responsibility per class/module.
- **Testability:** business logic isolated from framework and I/O so it can be unit tested without a live database.
- **Documentation:** OpenAPI/Swagger auto-generated and kept accurate by construction (schema-first via Pydantic).

---

## 5. Architecture Overview

### 5.1 Style: Modular Monolith, Layered Internally

A single deployable service, internally divided into **modules** by domain (auth, users, projects, tasks, notifications), each of which is internally **layered**:

```
project_root/
  app/
    core/            # config, DB session, Redis client, logging setup, security utils
    common/          # shared exceptions, base schemas, pagination helpers
    auth/
      router.py      # HTTP layer: request/response only
      service.py     # business logic: registration, login, token issuance
      repository.py  # persistence access for auth-related entities
      schemas.py      # Pydantic request/response models
      models.py       # SQLAlchemy models (User, tokens if persisted)
    projects/
      router.py
      service.py
      repository.py
      schemas.py
      models.py
    tasks/
      router.py
      service.py
      repository.py
      schemas.py
      models.py
    notifications/
      service.py      # email sending abstraction
    main.py            # app factory, router registration, middleware
  tests/
  alembic/             # migrations
```

Each module follows the same internal flow: **router -> service -> repository -> model**. Routers never talk to the database directly; services never import framework request/response objects; repositories are the only layer that knows about SQLAlchemy.

### 5.2 Why This Satisfies DRY and SOLID

- **Single Responsibility:** routers handle HTTP concerns only, services hold business rules, repositories hold persistence, schemas hold validation/serialization shape.
- **Open/Closed:** new task filters or new auth flows can be added by extending a service method rather than modifying unrelated code.
- **Liskov Substitution:** repositories are written against small, explicit interfaces so a repository could be swapped (e.g., an in-memory fake for tests) without breaking the service layer.
- **Interface Segregation:** schemas are split per use case (e.g., `TaskCreate`, `TaskUpdate`, `TaskRead`) rather than one bloated model doing everything.
- **Dependency Inversion:** services depend on repository interfaces, injected via FastAPI's dependency injection, not on concrete database sessions directly. This is also what keeps unit tests fast, since the DB layer can be mocked.
- **DRY:** shared concerns (pagination, error handling, timestamp mixins, the "current user" dependency) live once in `core`/`common` and are reused across modules rather than copy-pasted.

### 5.3 Cross-Cutting Concerns

- **Error handling:** a single exception-to-HTTP-response mapping registered on the app, so every module raises domain exceptions (`TaskNotFoundError`, `InvalidCredentialsError`) and the response shape is consistent everywhere.
- **Logging:** structured (JSON) logs with a request ID injected by middleware, propagated into every log line for that request, so a single request can be traced end to end across auth, task, and notification calls.
- **Configuration:** environment-driven via a settings object (Pydantic `BaseSettings`), never hardcoded, documented in `.env.example`.

---

## 6. Schema Design Deep Dive

### 6.1 Entity Overview

- **User** — account holder, owns projects.
- **Project** — a grouping of tasks, owned by a user.
- **Task** — the core unit of work, belongs to a project.
- **EmailVerificationToken** and **PasswordResetToken** are handled primarily in Redis (see Section 7), not as permanent database tables, since they are short-lived and disposable by nature. This avoids polluting the relational schema with rows that exist only for minutes.

### 6.2 Tables

**users**

| Column | Type | Notes |
|---|---|---|
| id | UUID, PK | |
| email | citext/varchar, unique, not null | indexed |
| password_hash | varchar, not null | Argon2/bcrypt hash, never plaintext |
| full_name | varchar, not null | |
| is_email_verified | boolean, default false | flips true after verification |
| is_active | boolean, default true | soft-disable without deleting |
| created_at | timestamptz, default now() | |
| updated_at | timestamptz, auto-updated | |
| deleted_at | timestamptz, nullable | null = active; set = soft-deleted (see Section 13) |

**projects**

| Column | Type | Notes |
|---|---|---|
| id | UUID, PK | |
| owner_id | UUID, FK -> users.id | indexed |
| name | varchar, not null | |
| description | text, nullable | |
| created_at | timestamptz | |
| updated_at | timestamptz | |
| deleted_at | timestamptz, nullable | null = active; set = soft-deleted |

**tasks**

| Column | Type | Notes |
|---|---|---|
| id | UUID, PK | |
| project_id | UUID, FK -> projects.id, not null | indexed |
| title | varchar(255), not null | |
| description | text, nullable | |
| status | enum('todo','in_progress','done'), default 'todo' | indexed for filtering |
| priority | enum('low','medium','high'), default 'medium' | indexed for filtering |
| due_date | date, nullable | |
| created_at | timestamptz, default now() | |
| updated_at | timestamptz, auto-updated | |
| deleted_at | timestamptz, nullable | null = active; set = soft-deleted |

**Indexes worth calling out:** composite index on `(project_id, status)` for the common "tasks in this project by status" query; index on `users.email` for login lookups. Since every table now carries `deleted_at`, the practical indexes are **partial indexes** scoped to `WHERE deleted_at IS NULL`, e.g. a partial unique index on `users.email` so a soft-deleted account doesn't block re-registration with the same address, and a partial index on `(project_id, status)` for active tasks only, since that is the filter every list-tasks query will apply first.

### 6.3 Relationships

- `users 1 --- * projects` (a user owns many projects)
- `projects 1 --- * tasks` (a project contains many tasks)
- Deletes are soft across the board: setting `deleted_at` on a project also stamps `deleted_at` on its tasks in the same transaction (application-level cascade, not a DB-level `ON DELETE CASCADE`, since nothing is actually removed). Deleting a user similarly soft-deletes the user row; their projects and tasks are left as-is unless explicitly cleaned up, since the audit trail is the point of soft-deleting in the first place.

---

## 7. Authentication Design Deep Dive

### 7.1 Flows

**Registration**
1. Client submits email, password, full name.
2. Service validates uniqueness of email, hashes password, creates the user row with `is_email_verified = false`.
3. Service generates a random verification token, stores it in Redis as `email_verify:{token} -> user_id` with a TTL (e.g., 24 hours).
4. Notification service sends an email containing a verification link with the token.

**Email Verification**
1. Client hits the verification endpoint with the token.
2. Service looks up `email_verify:{token}` in Redis. If missing or expired, return an error.
3. If found, mark the user's `is_email_verified = true`, delete the Redis key (single use).

**Login**
1. Client submits email and password.
2. Before checking credentials, service checks a Redis lockout key, e.g. `login_lock:{email}`. If present, reject immediately with a "too many attempts, try again later" response.
3. Service checks a Redis attempt counter, e.g. `login_attempts:{email}`, incremented on each failed attempt with a sliding TTL.
4. On failed credential check: increment `login_attempts:{email}`. If the count reaches the threshold (e.g., 5), set `login_lock:{email}` with a 15-minute TTL and reset the attempt counter.
5. On successful credential check: verify `is_email_verified` is true (block login otherwise, with a clear message), clear both Redis keys for that email, issue a short-lived JWT access token and a longer-lived refresh token.

**Forgot Password**
1. Client submits email.
2. Service generates a reset token, stores `pwd_reset:{token} -> user_id` in Redis with a short TTL (e.g., 15-30 minutes).
3. Notification service emails the reset link. Response is identical whether or not the email exists, to avoid leaking which emails are registered.

**Reset Password**
1. Client submits the token and a new password.
2. Service looks up `pwd_reset:{token}` in Redis. If missing/expired, reject.
3. If valid, hash and update the password, delete the Redis key, and invalidate any existing refresh tokens for that user (force re-login everywhere).

### 7.2 Why Redis for All of This

Redis is a natural fit because every artifact above (verification tokens, reset tokens, attempt counters, lockout flags) is short-lived and needs an expiry, which Redis provides natively via `EXPIRE`/`SETEX` without a background cleanup job. It also keeps the relational schema clean, since none of these are permanent records worth querying or joining against later.

### 7.3 Token Strategy

- **Access token:** JWT, short TTL (e.g., 15 minutes), carries user id and a token version/claim used to support revocation.
- **Refresh token:** longer TTL (e.g., 7 days), stored server-side (or its hash) so it can be revoked on password reset or logout.
- **Password hashing:** Argon2id preferred, bcrypt as a fallback if the environment can't install Argon2 bindings.

---

## 8. Logging Strategy

- Structured JSON logs, one line per log event, shipped to stdout (container-friendly).
- Middleware assigns a `request_id` (UUID) per incoming request and injects it into the logging context so every log line for that request can be correlated.
- Log levels: `DEBUG` for local development detail, `INFO` for normal request lifecycle events, `WARNING` for recoverable issues (e.g., failed login attempt), `ERROR` for unhandled exceptions and integration failures (e.g., email provider down).
- Explicitly never log: raw passwords, password hashes, full JWTs, or verification/reset tokens. Only log identifiers (user id, request id, event type).
- A single logging configuration module in `core/` is imported everywhere, so log format is consistent app-wide (DRY).

---

## 9. Git Strategy and Contribution Workflow

### 9.1 Branching Model

- `main` — production. Protected on GitHub: PRs required, direct pushes blocked (including for admins), force-push and branch deletion disabled. Deploys to production (Section 18).
- `dev` — staging/integration branch. Every feature branch merges here first; deploys to staging. Not force-pushed or deleted either, but doesn't carry the same hard protection as `main` since it's meant to move fast.
- `feature/<short-description>` — one branch per unit of work (e.g., `feature/task-crud`, `feature/auth-login`), branched off `dev`, PR'd back into `dev`.
- `fix/<short-description>` — bug fixes, same flow as `feature/*`.
- `chore/<short-description>` — tooling, CI, dependency bumps, same flow as `feature/*`.

**Promotion flow:** `feature/*` → PR → `dev` (staging). Once `dev` is in a state worth shipping, a separate PR promotes `dev` → `main` (production). This is a deliberate two-stage promotion rather than trunk-based development directly against `main`, so staging and production can be deployed independently from their respective branches.

### 9.2 Commit Convention

Conventional Commits style, so history is scannable and could drive automated changelogs later:

- `feat: add task creation endpoint`
- `fix: correct due_date validation`
- `docs: update README setup steps`
- `test: add unit tests for auth service`
- `chore: configure alembic migrations`

### 9.3 Pull Request Workflow

1. Branch off `dev`, keep the branch focused on one concern.
2. Push the branch, open a PR targeting `dev` with a clear description of what and why.
3. CI runs lint (ruff/flake8), type checks (mypy, optional), and the test suite on every push.
4. At least one review pass before merge (self-review is acceptable for a solo assessment, but the checklist still applies).
5. Squash-merge into `dev`.
6. Once `dev` holds a coherent, working slice, open a second PR promoting `dev` → `main`; merging this is what ships to production.
7. Tag releases using semantic versioning once the API is stable enough to version (`v0.1.0`, etc.).

### 9.4 Repository Hygiene

- `.env.example` committed, `.env` gitignored.
- `README.md` covers overview, setup, environment variables, how to run, endpoint list, assumptions, and known limitations, exactly as the assessment requires.
- `CONTRIBUTING.md` (even for a solo project) documents the branch/commit conventions above so the video walkthrough can reference it as evidence of process discipline.

---

## 12. Email Delivery: Gmail SMTP

Verification and password-reset emails are sent through a personal Gmail account using SMTP, via an **App Password** rather than the real account password (Gmail blocks plain password auth for third-party apps by default).

**Setup steps (documented in the README, not hardcoded anywhere):**

1. Enable 2-Step Verification on the Gmail account.
2. Generate an App Password under Google Account -> Security -> App passwords, scoped to "Mail."
3. Store the address and the generated app password as environment variables, never the real account password.

**Implementation notes:**

- Use `smtplib` with `SMTP_SSL` on port 465, or `SMTP` with `starttls()` on port 587. Port 587 with STARTTLS is the more portable default across hosting providers that block 465.
- Wrap sending in the `notifications` module (Section 5.1) behind a small interface (`EmailSender.send(to, subject, body)`), so the concrete Gmail SMTP client is swappable later for a transactional provider (SES, Postmark, Resend) without touching `auth/service.py`. This is the Dependency Inversion principle applied to a real integration point.
- Emails are sent asynchronously relative to the request where possible (e.g., via FastAPI `BackgroundTasks` for this scale of project), so registration and forgot-password endpoints don't block on SMTP latency.
- Failures to send should be logged as `WARNING`/`ERROR` but must not leak SMTP credentials or the raw token into logs (Section 8).
- Gmail's sending limits (roughly 500 messages/day on a standard account) are more than sufficient for an assessment or small-scale deployment, but this should be called out in the README as a known limitation, not something to rely on at production volume.

---

## 13. Soft Delete Strategy

Every table (`users`, `projects`, `tasks`) carries a nullable `deleted_at timestamptz` column instead of being physically removed on delete. `deleted_at IS NULL` means the row is active.

**Why:** preserves audit history, allows "undo delete" later, and avoids a DELETE endpoint accidentally destroying data referenced elsewhere (e.g., a task referenced in a report or a notification log).

**How it's implemented cleanly (keeps DRY):**

- A shared `SoftDeleteMixin` in `core/` adds `deleted_at` to every model, plus `is_deleted` as a computed property.
- A shared repository base class implements `.delete(id)` as `UPDATE ... SET deleted_at = now()` rather than a real `DELETE`, and every read method (`get_by_id`, `list`, etc.) filters `deleted_at IS NULL` by default, so soft-deleted rows are invisible to normal queries without every service having to remember to filter them out manually.
- The DELETE endpoints in the API keep their standard REST semantics (`204 No Content` on success, `404` if already deleted or never existed) — the soft-delete detail is entirely an implementation choice, invisible to the API consumer.
- A restore path (e.g., `POST /tasks/{id}/restore`) is a reasonable bonus feature to mention as a "known limitation not implemented" if time runs out, since the reviewers may ask about it given `deleted_at` is in the schema.

---

## 14. Configuration and Environment Variables

All configuration is loaded through a single Pydantic `BaseSettings` object in `core/config.py`, so nothing is hardcoded and every variable is documented, validated, and typed in one place.

| Variable | Example | Purpose |
|---|---|---|
| `ENVIRONMENT` | `local` / `staging` / `production` | Toggles debug behaviour, log verbosity |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@localhost:5432/taskdb` | Postgres connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection for tokens, lockouts |
| `JWT_SECRET_KEY` | `<random 64-char secret>` | Signs access/refresh tokens |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `LOGIN_MAX_ATTEMPTS` | `5` | Failed logins before lockout |
| `LOGIN_LOCKOUT_MINUTES` | `15` | Lockout duration after threshold is hit |
| `EMAIL_VERIFICATION_TTL_HOURS` | `24` | Verification token lifetime in Redis |
| `PASSWORD_RESET_TTL_MINUTES` | `30` | Reset token lifetime in Redis |
| `GMAIL_USER` | `yourapp@gmail.com` | Sending account |
| `GMAIL_APP_PASSWORD` | `<16-char app password>` | Gmail App Password, never the real password |
| `MAIL_FROM_NAME` | `Task Manager` | Friendly sender name |
| `FRONTEND_URL` | `http://localhost:3000` | Base URL used to build verification/reset links |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

`.env.example` ships in the repo with every key above and a placeholder value; `.env` itself is gitignored. The README documents each variable in the same table form so a reviewer can get the project running without guessing.

---

## 15. Developer Documentation and Contribution Setup

The project ships its own `README.md` and `CONTRIBUTING.md` (not just this design document, which is planning material). Their contents:

**README.md covers:**
- Project overview and tech stack.
- Prerequisites (Python version, Docker, Docker Compose).
- Quick start: `docker compose up` for API + Postgres + Redis together, and a bare-metal alternative (virtualenv, `pip install -r requirements.txt`, `alembic upgrade head`, `uvicorn app.main:app --reload`).
- Full environment variable table (Section 14).
- How to run migrations, how to seed sample data.
- Full endpoint list (or a link to `/docs` for the live Swagger UI).
- How to run tests (Section 16) and how to read coverage output.
- Assumptions and known limitations (Section 11).
- Deployment notes (Section 18), or a link to it.

**CONTRIBUTING.md covers:**
- Branch naming and commit convention (Section 9).
- Local dev setup, identical to the README's quick start but framed for someone about to write code, not just run it.
- Pre-commit hooks: `ruff` (lint), `black` (format), `isort` (import order), `mypy` (type checking) run automatically via a `pre-commit` config, so style issues never reach CI.
- Expectation that new endpoints/services come with tests in the same PR.
- How to open a PR and what the CI pipeline checks before merge is allowed.

Both files are generated as part of the actual project deliverable, not left as an afterthought, since the assessment explicitly grades README quality.

---

## 16. Test Strategy

Tests are split into three tiers, mirroring the layered architecture in Section 5:

| Tier | What it covers | Speed | DB/Redis needed? |
|---|---|---|---|
| **Unit** | Service-layer business logic (registration rules, lockout math, task validation) with repositories mocked/faked | Fast, milliseconds | No |
| **Integration** | Repository layer against a real Postgres (and Redis for auth flows), verifying queries, constraints, and soft-delete filtering actually behave as designed | Slower, seconds | Yes, real instances |
| **API / contract** | Full request/response cycle via FastAPI's `TestClient`, hitting real routers end to end, asserting status codes and response shape | Moderate | Yes |

**Practical setup:**

- `pytest` as the runner, `pytest-asyncio` for async test functions, `httpx.AsyncClient` or FastAPI's `TestClient` for API tests.
- A dedicated test database (`taskdb_test`) and a dedicated Redis DB index (e.g., `redis://localhost:6379/1`), never the dev database, so tests can freely create and tear down data.
- Each test wraps its DB work in a transaction that's rolled back at the end, keeping tests isolated and fast even at the integration tier.
- `pytest` markers (`@pytest.mark.unit`, `@pytest.mark.integration`) so CI can run the fast unit tier on every push and the slower integration tier as a required check before merge.
- A minimum coverage threshold (e.g., 80% on the `service` and `core` layers specifically, since routers and models are largely declarative and less valuable to chase for coverage) enforced via `pytest-cov` and failing the CI job if not met.
- Specific scenarios worth explicit test cases: login lockout triggers after the configured attempt count and clears after the lockout window; an expired verification/reset token is rejected; a soft-deleted task never appears in list results; task filtering and pagination return correct counts at page boundaries.

---

## 17. CI/CD Pipeline

A single GitHub Actions workflow, triggered on pushes and pull requests to `main`:

**CI (runs on every push/PR):**
1. **Setup** — checkout code, set up Python, cache pip dependencies.
2. **Lint & format check** — `ruff check .`, `black --check .`, `isort --check-only .`.
3. **Type check** — `mypy app/`.
4. **Unit tests** — fast tier, no services needed, runs first so failures surface quickly.
5. **Integration tests** — spin up Postgres and Redis as GitHub Actions `services:` containers, run `alembic upgrade head` against the test DB, then run the integration and API test tiers with coverage.
6. **Coverage gate** — fail the build if coverage drops below the agreed threshold.
7. **Build check** — build the Docker image (Section 18) to confirm it builds cleanly, without pushing it yet.

**CD (runs on merge to `main`, after CI passes):**
1. Build the production Docker image, tag it with the short commit SHA and `latest`.
2. Push to a container registry (GitHub Container Registry is the simplest choice since it needs no extra account, and pairs naturally with a GitHub Actions pipeline).
3. Trigger a deploy on the chosen platform (Section 18), either via that platform's GitHub integration (auto-deploy on new image) or a deploy hook called from the workflow.
4. Run a smoke test against the deployed `/health` endpoint before considering the deploy complete; a failed smoke test should be visible in the Actions run, not silently ignored.

This keeps the pipeline honest: nothing reaches `main` without passing lint, types, and both test tiers, and nothing reaches production without a green CI run on `main` first.

---

## 18. Deployment Strategy

**Recommendation: containerized deployment on Render or Railway**, both of which offer managed Postgres and Redis add-ons alongside a Docker-deployable web service, with zero infrastructure to hand-manage. This matches the project's scale (an assessment/small-scale service, not something needing Kubernetes-level orchestration) and keeps the "how to deploy" story simple enough to explain clearly in the video walkthrough.

- **Dockerfile:** multi-stage build, a `builder` stage that installs dependencies into a virtualenv, and a slim final stage that copies only the built virtualenv and app code, keeping the production image small and free of build tooling.
- **docker-compose.yml (local/dev only):** three services, `api`, `db` (Postgres), `redis`, wired together with a `.env` file, so a reviewer can run the entire stack with one command.
- **Migrations on deploy:** `alembic upgrade head` runs as a release/pre-deploy step, not inside the running container's startup path, so a failed migration blocks the deploy rather than crash-looping the app.
- **Secrets:** all values from Section 14's env table are set as platform-level environment variables/secrets, never committed, never baked into the image.
- **Health check:** a `/health` endpoint (checks DB and Redis connectivity) wired into the platform's health check config, so a broken deploy is caught and rolled back automatically rather than served to users.
- **Scaling note:** if this grew past an assessment into something with real traffic, the natural next step is a managed Postgres with connection pooling (PgBouncer or the platform's built-in pooler), and moving from Render/Railway to AWS ECS/Fargate or similar once the team needs finer infrastructure control. That's explicitly out of scope here and is noted as a "known limitation" in the README rather than something over-engineered up front.

---

## 19. Delivery Checklist Against the Assessment Brief

- [ ] All five CRUD endpoints for tasks, validated, correct HTTP status codes.
- [ ] PostgreSQL via SQLAlchemy ORM, Alembic migrations.
- [ ] FastAPI project structured as a modular monolith per Section 5.
- [ ] Auth: register, verify email, login, forgot password, reset password.
- [ ] Redis-backed login attempt lockout (15 minutes after threshold reached).
- [ ] Structured logging with request correlation.
- [ ] Automated tests for service-layer logic (mocked repositories) and at least a few integration tests against the real endpoints.
- [ ] Docker support (Dockerfile + docker-compose for API, Postgres, Redis).
- [ ] Swagger/OpenAPI docs (automatic via FastAPI).
- [ ] Pagination, filtering, and search on the list-tasks endpoint.
- [ ] Soft delete (`deleted_at`) on users, projects, and tasks, with partial indexes and repository-level filtering.
- [ ] Gmail SMTP email delivery for verification and password reset, via App Password.
- [ ] README.md and CONTRIBUTING.md shipped in the repo covering setup, env vars, run steps, endpoint list, testing, deployment, assumptions, limitations.
- [ ] Pre-commit hooks (ruff, black, isort, mypy) configured.
- [ ] Three-tier test suite (unit, integration, API) wired into CI with a coverage gate.
- [ ] GitHub Actions CI/CD pipeline: lint, type-check, test, build, and deploy on merge to `main`.
- [ ] Deployment live on Render/Railway (or documented deploy steps if not actually deployed within the deadline).
- [ ] 3-5 minute video walkthrough: running app, core functionality, architecture explanation.

---

## 20. Assumptions and Open Questions

- A "project" entity is introduced even though it isn't explicitly listed in the field requirements, because the brief describes tasks as existing "within a project." This will be called out explicitly in the README as an assumption.
- Multi-tenancy (teams sharing a project) is out of scope; each project belongs to exactly one user for this version.
- Email delivery uses a personal Gmail account via SMTP with an App Password, which is fine for an assessment and low volume, but is explicitly noted in the README as not the right choice for production-scale sending (a transactional provider would replace it behind the same `EmailSender` interface).
- Deployment target is Render or Railway for simplicity; if time doesn't allow an actual live deploy before the deadline, the Dockerfile, docker-compose setup, and deployment steps in Section 18 will still be fully documented and demonstrated locally in the video walkthrough.
