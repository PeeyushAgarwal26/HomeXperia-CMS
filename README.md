# homexperia-backend

FastAPI backend for the HomeXperia admin CMS rebuild. Architecture mirrors
`axiot_backend_module` — see the design docs in the `homexperia` docs repo:
`01-overview.md`, `02-database-schema.md`, `03-backend-architecture.md`,
`04-api-reference.md` for the full rationale and every planned endpoint.

## What's here right now

Shared infrastructure, the full database schema (all 7 tables from
`docs/02-database-schema.md`), and one-command environment bootstrap — no
feature endpoints yet (no login, no Sub-Admin CRUD):

- `app/core/` — settings (`config.py`), password hashing + JWT helpers (`security.py`)
- `app/db/` — SQLAlchemy async engine/session, `BaseModel`/`SoftDeleteMixin`
- `app/common/` — `BaseRepository`/`BaseService`/`BaseController`, the
  `APIResponse` envelope, pagination params, request-context, structlog
  setup, the local-disk `StorageInterface`
- `app/middleware/` — request-context/trace-id middleware
- `app/exceptions/` — typed exceptions + global exception handlers
- `app/modules/{geo,module_catalog,admin_users,auth,activity_logs}/models.py`
  — the real ORM models for `states`, `modules`, `admin_users`,
  `admin_user_module_permissions`, `refresh_tokens`, `password_reset_tokens`,
  `activity_logs`. No `schemas.py`/`repository.py`/`service.py`/`controller.py`
  yet — no endpoints, just the tables.
- `alembic/versions/` — the first migration, creating all 7 tables
- `scripts/seed_reference_data.py` — seeds `states` (36) + the `modules`
  catalog tree (24 entries), idempotent
- `scripts/create_superadmin.py` — creates the one super admin account
  (there's no create-account page in this admin panel, matching the
  reference UI — this script is the only way one comes into existence)
- `homexperia_v1.sql` — a `pg_dump` snapshot of the schema + `states`/
  `modules` seed data, for reference or a fast manual import. Alembic
  migrations remain the source of truth; regenerate this file per the
  instructions in its header after adding a migration.
- `app/main.py` — app factory with just a `/health` endpoint wired up

## Setup

One command on a fresh machine, given a running local Postgres:

```bash
./setup.sh setup
```

Prompts for DB host/port/name/user/password and super admin details
(username/password/name/email/phone/pin code/state code/city), then:
creates the venv, installs dependencies, writes `.env` (with an
auto-generated `SECRET_KEY`), creates the database if missing, runs Alembic
migrations, seeds states + the module catalog, and creates the super admin.

Run it again later and it detects the database already has tables, and asks
whether to **keep** existing data (just applies any new migrations) or
**drop and recreate** from scratch.

Every prompt can be skipped for CI/non-interactive use — see
`./setup.sh help` for the full list of env vars (`DB_HOST`, `DB_NAME`,
`SUPERADMIN_USERNAME`, `DB_RESET_CHOICE=k|d`, etc).

```bash
./setup.sh start     # background, hot-reload, logs → uvicorn.log
./setup.sh status
./setup.sh logs       # tail -f
./setup.sh stop
./setup.sh restart
./setup.sh reset      # DROP + recreate the database, re-seed, new super admin
```

`http://localhost:8000/docs` for the interactive API docs (nothing to call
yet beyond `/health`).

## Adding a new module

See "Adding a new module" in `docs/03-backend-architecture.md`. Short
version: create `app/modules/<name>/{models,schemas,repository,service,controller}.py`,
import its `models.py` in `app/db/models.py`, register its router in
`app/api/v1/router.py`, then generate a migration:

```bash
alembic revision --autogenerate -m "add_<module>"
alembic upgrade head
```

## Branching

`main` is always deployable. `development` is the integration branch — cut
`feature/<short-name>` branches from `development`, PR back into
`development` when done. `main` only moves via a release merge from
`development`.
