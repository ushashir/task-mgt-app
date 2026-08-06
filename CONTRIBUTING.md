# Contributing

This is a solo technical-assessment project, but it follows the same process discipline a team project would -- partly because that's good practice, partly so the git history itself demonstrates the workflow during the technical discussion. If you're picking this up to extend it, this is what "about to write code" setup looks like.

## Branching model

- **`main`** = production. Protected on GitHub: pull requests required, no direct pushes (not even for the repo owner/admin), no force-push, no branch deletion.
- **`dev`** = staging/integration. Every feature branch targets this first.
- **`feature/<short-description>`**, **`fix/<short-description>`**, **`chore/<short-description>`** -- one branch per unit of work, branched off `dev`.

Flow:

```
feature/my-thing  ──PR──▶  dev  ──PR (once dev is stable)──▶  main
```

1. Branch off `dev`: `git checkout dev && git pull && git checkout -b feature/short-description`.
2. Commit, push, open a PR targeting `dev`.
3. CI (lint, type-check, unit tests, then integration/API tests with a coverage gate, then a Docker build check) must pass.
4. Squash-merge into `dev`.
5. Once `dev` holds a coherent, working slice, a separate PR promotes `dev` -> `main` -- that's the only thing that ships to production.

## Commit convention

[Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add task creation endpoint
fix: correct due_date validation
docs: update README setup steps
test: add unit tests for auth service
chore: configure alembic migrations
```

No AI-attribution or co-author trailers.

## Local dev setup

```bash
git clone https://github.com/ushashir/task-mgt-app.git
cd task-mgt-app
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install

cp .env.example .env   # fill in DATABASE_URL/REDIS_URL for instances you're running

docker compose up -d db redis   # or run your own Postgres 16 / Redis 7
alembic upgrade head
uvicorn app.main:app --reload
```

Full command reference (lint, tests, etc.) is in the [README](./README.md#testing).

## Pre-commit hooks

`.pre-commit-config.yaml` runs `ruff` (lint), `black` (format), `isort` (import order), and `mypy` (type check) on every commit, so style issues never reach CI:

```bash
pre-commit install        # one-time, per clone
pre-commit run --all-files   # run manually against everything
```

Note: `ruff`'s own import-sorting rule is deliberately disabled in `pyproject.toml` -- `isort` is the single source of truth for import order. Running both against the same rule caused them to disagree and fight over the same lines.

## What a PR needs

- New endpoints or services come with tests in the *same* PR -- unit tests at minimum; add integration/API tests if the change touches a repository query or a full request/response contract.
- `mypy app/` passes in strict mode. `tests/` is excluded from strict typing (see `pyproject.toml`), but should still be lint/format-clean.
- If you're touching the schema, include the Alembic migration and confirm `alembic upgrade head` / `alembic downgrade -1` both work against a real Postgres instance -- migrations that only work in one direction have bitten this project before (see the ENUM-type cleanup in `alembic/versions/*_create_users_projects_tasks_tables.py` for an example of what autogenerate misses).
- Self-review is fine for a solo contributor; the checklist above still applies to yourself.

## What CI checks

See the [README's CI/CD section](./README.md#cicd) for the full pipeline. In short: lint/format/type-check -> unit tests -> integration+API tests against real Postgres/Redis service containers with an 80% coverage gate -> a Docker build check. A PR into `dev` or `main` won't be mergeable (branch protection on `main`; convention on `dev`) until all of that is green.
